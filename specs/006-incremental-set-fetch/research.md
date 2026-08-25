# Research: Incremental Per-Set Match Fetching & Recovery

## 1. Fetching an event's set_id list cheaply

**Decision**: Add a new, minimal GraphQL query (`get_event_set_ids_query()` in
`scripts/queries.py`) that requests only `sets(page, perPage) { pageInfo { total
totalPages } nodes { id } } }` under `event(id: $eventId)`. Fetched via the existing
`fetch_all_nodes()` helper (paginated, retried), exactly like today's bulk sets query,
but with a field selection of just `id` instead of the full `_SET_NODE_FIELDS`/
`_SET_NODE_FIELDS_LIGHT` set (which include `slots`, `games`, `selections`, etc.).

**Rationale**: The original failure (`grand_slum`: `total_pages=1267` at
`max_pages=200`; `SHIBUYA_DAIRAN`: `total_pages=510`) comes from start.gg's per-request
GraphQL complexity limit, which scales with how many nested fields are requested per
node × how many nodes per page. An ID-only projection has a small, fixed per-node cost,
so far more sets fit in a single page before hitting the complexity ceiling — this
listing step is expected to comfortably paginate to completion even for the largest
observed events (spec.md Assumptions).

**Alternatives considered**:
- Reuse the existing `get_event_sets_light_query()` (`_SET_NODE_FIELDS_LIGHT`) for
  listing. Rejected: still requests `slots`, `games`, `phaseGroup` per node — the same
  category of complexity blowup as the full query, just scaled down, not eliminated.
- Derive the set count from `standings`/`seeds` entrant counts instead of a dedicated
  query. Rejected: entrant count doesn't give individual `set_id`s, which are required
  to seed placeholders (FR-002) and to detect outstanding work (FR-007).

## 2. Fetching a single set's full detail directly by ID

**Decision**: Fetch each outstanding set's full detail via start.gg's top-level
`set(id: ID!): Set` query field, reusing the existing `_SET_NODE_FIELDS` selection,
rather than continuing to page through `event.sets` or `phaseGroup.sets`.

**Rationale**: Confirmed via start.gg's published GraphQL schema reference
(`developer.start.gg` → `smashgg-schema.netlify.app/reference/query.doc.html`) that the
root `Query` type exposes `set(id: ID!): Set` alongside `event`, `phaseGroup`,
`phase`, etc. Fetching by ID means each request's complexity is bounded by the fixed
shape of `_SET_NODE_FIELDS` — independent of the event's total set count or which
phase/pool the set belongs to. This is what makes progress genuinely incremental
(FR-003): no request ever needs to "see" the whole event at once again.

**Alternatives considered**:
- Keep paging through `event.sets`/`phaseGroup.sets` (today's approach,
  `_fetch_all_sets_by_phase_group` / `_fetch_sets_with_fallback` in `download.py`) but
  checkpoint by page number instead of by `set_id`. Rejected: an event with a single
  huge pool phase can still blow the complexity budget on page 1 regardless of
  checkpointing granularity (this is exactly why `excluded_phases.json` already exists
  as a manual escape hatch for known-bad phase groups) — checkpointing by page doesn't
  fix the root cause, it only shrinks the blast radius.
- Batch fetches via `phaseGroup.sets` with a very small `per_page` (e.g. 1) as a
  cheaper way to "page one set at a time" without a new query. Rejected: still pays
  the per-request overhead of resolving the phaseGroup pagination machinery, and, per
  `SETS_PER_PAGE_FALLBACKS = (50, 25, 10, 5, 3, 1)`, `per_page=1` is already the last
  resort in the existing fallback ladder and is known to sometimes still fail on
  pathological phase groups (hence `excluded_phases.json`). Fetching by `set_id`
  directly avoids phase/pool pagination entirely.

## 3. Batching multiple sets per request

**Decision**: Fetch outstanding sets in small batches per HTTP request using GraphQL
field aliasing against the same `set(id:)` field (e.g. `s0: set(id: $id0) { ... } s1:
set(id: $id1) { ... }`), with a batch size in the same order of magnitude as the
existing `SETS_PER_PAGE_FALLBACKS` values (tens, not hundreds) — exact size to be
tuned in Phase 2 (tasks) against observed complexity costs, with a fallback-to-smaller
strategy analogous to `_fetch_sets_with_fallback`'s existing pattern for consistency
(Constitution Principle V: no bespoke retry logic, but request *shaping* — how many
sets per request — is this feature's own concern, distinct from retry/backoff).

**Rationale**: A batch of 1 set per request is correctness-safe but would mean
thousands of individual HTTP round-trips (plus inter-request `page_delay`) to fully
backfill a `grand_slum`-sized event, risking the same GitHub Actions 60-minute job
timeout that (independently) already caused several `data_gap_check` runs to be
cancelled outright (see prior investigation in this session: runs on 2026-08-02,
2026-08-09, 2026-08-16 were killed mid-`Download` step). Batching amortizes per-request
overhead while keeping each request's complexity bounded and predictable (batch size ×
fixed per-set cost), unlike the old approach where complexity scaled with the *event's*
total set count.

**Alternatives considered**:
- Fixed batch size with no fallback. Rejected: different events may have different
  per-set complexity (e.g. sets with many games/selections vs. simple ones), so a
  fallback ladder (mirroring `SETS_PER_PAGE_FALLBACKS`) is more robust than a single
  hardcoded constant, consistent with how the rest of `download.py` already handles
  this class of problem.

## 4. Placeholder record representation & outstanding-work detection

**Decision**: A placeholder record in `matches.json` is a dict containing only
`{"set_id": <int>}`. A complete record is today's existing shape (`winner_id`,
`loser_id`, `winner_score`, ..., `details`) plus the new `set_id` field. "Outstanding"
is computed by scanning `matches.json`'s `data` list for records whose only key is
`set_id` (equivalently: records missing `winner_id`). Replacing a placeholder is an
in-place list update keyed by `set_id`, not an append (FR-008).

**Rationale**: Matches spec.md's Key Entities description exactly ("only `set_id`
populated" vs. full shape) and keeps `matches.json` self-describing — no second file or
derived index needs to stay in sync with it.

**Alternatives considered**:
- Placeholder record with all fields present but `null` (e.g. `{"set_id": 1,
  "winner_id": None, ...}`). Rejected: makes "is this a placeholder" ambiguous against
  legitimate `null` values that already occur in complete records today (e.g. `dq`
  matches can have unusual scores; guest/unlinked entrants already produce `null`
  `winner_id`/`loser_id` in some rows per `docs/data_model.md`'s existing note on
  doubles/crew events). A key-presence check (`"winner_id" not in record`) cannot be
  confused with a legitimately-`null` `winner_id` on a complete record the way a
  value-based check (`record["winner_id"] is None`) can.

## 5. `EVENT_DATA_VERSION` bump and backfill integration

**Decision**: Bump `scripts/utils.py`'s `EVENT_DATA_VERSION` from `5` to `6`. Existing
events (whose `matches.json` records lack `set_id`, or whose `attr.json` is entirely
absent because they were interrupted under the old all-or-nothing fetch) are backfilled
by `scripts/fetch/backfill_schema_version.py`'s existing rolling/cyclic scan — no new
migration script. That scanner already discovers directories via `standings.json`
presence (not just `attr.json`), specifically so interrupted events (today: missing
`attr.json`) are found (see `iter_event_dirs()`'s docstring) — this property is what
lets FR-011's backfill naturally pick up events that were left incomplete by the old
bug, once they're re-processed through the new incremental path.

**Rationale**: Reuses the exact mechanism Constitution Principle I mandates ("既存デー
タへの影響がある場合は... MUST 移行する") and that already exists in this codebase for
this exact kind of change, rather than introducing a parallel one-off backfill tool.

## 6. Retiring `large-event-skip` / `fetch_large_event`

**Decision**: Delete `.github/workflows/fetch_large_event.yml`. Remove the
`max_pages`/`skip_report_path`/`MaxPagesExceededError`/`_record_skip` machinery and the
"Create large-event-skip issue" step in `data_gap_check.yml`, since no code path can
raise `MaxPagesExceededError` from set-fetching anymore once bulk `event.sets`/
`phaseGroup.sets` pagination for match detail is replaced by ID-based fetching (§2).

**Rationale**: FR-012/013 (spec.md) — confirmed by the user as a deliberate scope
decision during `/speckit-clarify`, not an oversight. Session investigation already
established the `large-event-skip` issue-creation path had never actually fired in
production (the `large-event-skip` GitHub label doesn't exist in the repo) due to an
unrelated, separately-fixed bug in `download_all_tournaments`'s early-return-on-
`finish_date` — so removing it sheds dead-in-practice operational surface, not a
working safety net.

**Note**: `MaxPagesExceededError` and `max_pages` may still be relevant to *other*
paginated queries this feature retains (e.g. the new ID-only set-listing query in §1,
`standings`, `seeds`) — only the *sets-detail-fetch*-triggered skip/report/issue path
is retired, not the `max_pages` mechanism itself.

## 7. Interaction with `scripts/fix/validate_data.py`

**Finding (not a design decision — confirmed by reading the code)**:
`validate_data.py` discovers event directories via `events_root.rglob("attr.json")` —
it never visits a directory that lacks `attr.json`. Since `attr.json` is only written
once no placeholders remain (FR-009), an event still being incrementally filled in is
invisible to today's validator and cannot produce false errors from partially-populated
`matches.json`. No change to `validate_data.py`'s discovery mechanism is required.

**Optional hardening (recommended, not required)**: Once `attr.json` exists for an
event, `validate_data.py` could additionally assert that `matches.json` contains zero
placeholder-shaped records (a `winner_id`-missing record) as a defensive invariant
check — catching a hypothetical future bug where `attr.json` gets written prematurely.
Left as a candidate task, not a blocking requirement.

## 8. Compliance with existing retry/backoff (Constitution Principle V)

**Decision**: Both new queries (§1 ID-listing, §2/§3 by-ID detail fetch) are issued
through `fetch_data_with_retries()` (single request) and, for the paginated listing
query, `fetch_all_nodes()` — the same helpers `download.py` already uses for every
other query. No new retry/backoff/complexity-detection logic is written.

**Rationale**: Directly required by Constitution Principle V; also means the existing
429/5xx handling in `fetch_data_with_retries()` (`docs/startgg_design.md` §ページング
とリトライ) applies unchanged to the new queries with no extra work.
