# Feature Specification: Incremental Per-Set Match Fetching & Recovery

**Feature Branch**: `006-incremental-set-fetch`

**Created**: 2026-08-25

**Status**: Draft

**Input**: User description: "途中で打ち切られた場合に結局データが保存されないのは困ります。complexityが高すぎるのが原因だったと思いますが、であれば中間ファイルとしてset_idだけ保存しておいて、setごとに後から埋めていく方式にしたい。matches.jsonにset_id（snake_caseでいいっけ？）も保存していくようにしたい。"

## Clarifications

### Session 2026-08-25

- Q: Once an event's set_id list is known, should it be re-checked against start.gg
  for changes (sets added/removed/replaced) while the event is still incomplete? → A:
  No — the known list is left alone during normal incremental fetching, whether the
  event is complete or not. It is only reconciled against start.gg's current set list
  when the event is picked up by the existing `event_data_version`-driven backfill
  cycle (the same rolling mechanism already used for schema-version backfills per
  FR-010/FR-011), not proactively on every run.
- Q: Should the set_id list be tracked in a separate intermediate file, or embedded
  directly in `matches.json`? → A: No separate file. `matches.json` itself is
  pre-populated with a placeholder record (containing only `set_id`) for every set
  belonging to the event before any set's full detail is fetched. Each placeholder is
  replaced in place, in `matches.json`, with the full match record as that set's
  detail is successfully fetched.

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Large events survive an interrupted fetch (Priority: P1)

As the maintainer of the data pipeline, when a large event's match data cannot be
fetched in a single pass because it exceeds the page/complexity limit, I want the
matches already retrieved before the interruption to be kept, so that a large event
never ends up with *zero* match data purely because of its size.

**Why this priority**: This is the exact failure observed in production (a 488-entrant
event ended up with standings and seeds but no `matches.json`/`attr.json` at all). It is
the core complaint driving this feature and blocks everything else.

**Independent Test**: Can be fully tested by fetching an event whose set-detail
retrieval is interrupted partway through, then verifying that the match records
successfully retrieved before the interruption are present in `matches.json` and are
not discarded.

**Acceptance Scenarios**:

1. **Given** an event whose set-detail fetch is interrupted after some sets have been
   successfully retrieved, **When** the interruption occurs, **Then** the match records
   for the sets already retrieved remain saved in `matches.json`.
2. **Given** an event that previously ended with a partial fetch, **When** the pipeline
   processes that event again, **Then** only the sets not yet recorded are fetched, and
   previously recorded match records are left unchanged.

---

### User Story 2 - Large events complete without manual recovery (Priority: P2)

As the maintainer, I want large events to reach full completion automatically through
the pipeline's normal scheduled runs, so that I no longer need to notice a GitHub issue
and manually trigger a separate recovery workflow just because an event was too big for
a single bulk fetch.

**Why this priority**: This retires the operational workaround (a GitHub issue plus a
manually-triggered `fetch_large_event` workflow run) that exists specifically because
today's bulk, single-pass sets fetch cannot handle large events. Once incremental
per-set fetching and cross-run resumption (User Stories 1 and 3) exist, that workaround
no longer has a reason to exist — large events just complete like any other event,
across however many runs it takes.

**Independent Test**: Can be fully tested by fetching a large event (one that
previously would have exceeded the bulk-fetch page limit) end-to-end using only the
pipeline's normal scheduled invocation, with no manual workflow trigger, and confirming
it reaches the same completed state (`matches.json` + `attr.json` present) as a small
event.

**Acceptance Scenarios**:

1. **Given** a large event that would have previously exceeded the bulk sets-fetch page
   limit, **When** the pipeline runs its normal scheduled processing (possibly across
   several runs), **Then** the event reaches full completion without any manual
   workflow being triggered and without a "large event" issue being filed.
2. **Given** this feature is in place, **When** the pipeline encounters an event too
   large to fetch in one pass, **Then** it is treated the same as any other in-progress
   event (tracked via its placeholder records in `matches.json` and resumed on
   subsequent runs) rather than being specially flagged for manual intervention.

---

### User Story 3 - Track which sets remain to be fetched (Priority: P3)

As the maintainer, I want `matches.json` itself to be pre-populated with a placeholder
entry for every set belonging to an event before full match details are fetched, so
that the pipeline (and I, when investigating) can tell which sets are still outstanding
for an event just by looking at `matches.json` — no separate file to cross-reference.

**Why this priority**: This is the mechanism that makes User Story 1's recovery
possible — without knowing the full expected set of `set_id`s up front, the pipeline
cannot tell "outstanding" apart from "this event legitimately has no more sets."

**Independent Test**: Can be fully tested by fetching only an event's set_id list
(without fetching full set details), confirming `matches.json` ends up with exactly
one placeholder record per set start.gg reports for that event, and that no full match
detail has been filled in yet.

**Acceptance Scenarios**:

1. **Given** an event that has not yet been fetched, **When** the pipeline begins
   processing it, **Then** `matches.json` is written with one placeholder record
   (`set_id` only) for every set belonging to the event, before any per-set match
   detail is fetched.
2. **Given** an event's `matches.json` contains a mix of placeholder and complete
   records, **When** the outstanding sets are computed, **Then** the result is exactly
   the `set_id`s whose record in `matches.json` is still a placeholder.

---

### User Story 4 - Match records are traceable to their source set (Priority: P4)

As the maintainer, I want every match record in `matches.json` to carry the start.gg
`set_id` it came from, so I can cross-reference a record against start.gg directly and
so records can be deduplicated/matched reliably by ID instead of by field comparison.

**Why this priority**: Valuable for debugging and for the resumability in User Story 1
(matching "already fetched" sets), but on its own does not fix the data-loss problem —
it's an enabler/quality improvement layered on top of Stories 1 and 2.

**Independent Test**: Can be fully tested by fetching any event's matches and
confirming each record in `matches.json` contains a `set_id` field matching a real
start.gg set for that event.

**Acceptance Scenarios**:

1. **Given** a newly fetched event, **When** `matches.json` is written, **Then** every
   match record includes a `set_id` field.
2. **Given** two distinct match records for the same event, **When** their `set_id`
   values are compared, **Then** they are different (each recorded set appears once).

---

### Edge Cases

- When start.gg's set list for an event changes after `matches.json` has already been
  seeded with placeholders (e.g., a set is added, removed, or replaced after a TO edits
  the bracket): the placeholders already in `matches.json` are not proactively
  re-checked against start.gg during normal incremental fetching. The change is only
  picked up the next time the event is reconciled through the
  `event_data_version`-driven backfill cycle (see Clarifications).
- When the per-set detail fetch fails for an individual `set_id` (e.g. a transient API
  error) after that set's placeholder has already been written to `matches.json`: only
  that placeholder is retried on a subsequent run; other already-completed records in
  the same `matches.json` are left untouched.
- An event's `matches.json` is always seeded with placeholder records up front,
  regardless of whether the rest of that event's set details end up being fetched in
  one run or spread across many — there is no separate "was the intermediate step run"
  question, since seeding and filling in both happen against the same file.
- How does the pipeline decide an event's match data is "complete" now that matches can
  arrive incrementally across multiple runs, given `attr.json` (which marks
  `archive_status: "completed"`) is currently only written after a single all-or-nothing
  fetch succeeds? (See FR-009: complete means no placeholder records remain.)
- What happens if the same `set_id`'s detail is fetched twice (e.g. due to a retry
  racing with a resumed run) — the second fetch MUST replace the same placeholder (or
  overwrite the same now-complete record) in place rather than appending a second
  record for that `set_id` (see FR-008).
- What happens if even fetching an event's `set_id` list (the one remaining paginated
  query in this design, used to seed placeholders) cannot complete for a
  pathologically large event? Since the existing max_pages-based safety net
  (large-event-skip issue + manual `fetch_large_event` workflow) is being retired
  rather than kept as a narrower fallback, such an event has no dedicated manual escape
  hatch under this feature — it relies on incremental per-set fetching and repeated
  scheduled runs to eventually converge, same as any other event.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST obtain the full list of `set_id`s belonging to an event
  as its own step, separate from fetching each set's full match detail (winner/loser,
  scores, games, character selections), in order to seed placeholder records before
  any detail is fetched.
- **FR-002**: The system MUST write `matches.json` with a placeholder record
  (containing only `set_id`) for every set belonging to an event before fetching any
  per-set match detail for that event — so the set of "sets to fetch" is visible
  directly in `matches.json`, even if detail fetching is interrupted, and remains
  known across separate, later pipeline runs (not only within the run that first
  seeded it).
- **FR-003**: The system MUST fetch full match detail for an event's sets
  incrementally (one set, or a small batch of sets, at a time) and, for each
  successfully fetched set, replace that set's placeholder record in `matches.json`
  with the full match record in place, rather than only after every set in the event
  has succeeded.
- **FR-004**: Every record in `matches.json` — placeholder or complete — MUST include
  a `set_id` field (snake_case, consistent with this file's existing field naming)
  identifying the start.gg set the record corresponds to; a placeholder record's
  `set_id` is retained unchanged when it is replaced with the full match record.
- **FR-005**: When fetching is interrupted partway through an event's sets (for any
  reason — complexity/page limit reached, process stopped, transient failure), the
  system MUST retain the match records already successfully replaced in `matches.json`
  for that event rather than discarding them; any remaining placeholders simply stay
  as placeholders.
- **FR-006**: When the pipeline processes an event that already has some complete
  records in `matches.json`, it MUST fetch detail only for the `set_id`s whose record
  is still a placeholder, and MUST NOT re-fetch sets whose record has already been
  replaced with full match detail.
- **FR-007**: The system MUST be able to determine, for a given event, which `set_id`s
  remain outstanding by scanning `matches.json` for records that are still
  placeholders (i.e., lack full match detail).
- **FR-008**: The system MUST NOT produce more than one record for the same `set_id`
  within an event's `matches.json`; fetching a set's detail MUST replace that set's
  existing record (placeholder or, if re-fetched, already-complete) in place rather
  than appending a new one, including when a fetch is retried or resumed.
- **FR-009**: The system MUST only consider an event's match data complete — and only
  then proceed to write `attr.json` with `archive_status: "completed"` — once no
  placeholder records remain in that event's `matches.json` (every record has been
  replaced with full match detail, or has been explicitly determined to be excluded,
  per existing exclusion handling).
- **FR-010**: The system MUST identify events whose already-saved match data predates
  this feature (and therefore lacks `set_id` on its match records) using the same
  version marker already used to detect outdated event schemas, and MUST treat those
  events as needing a backfill.
- **FR-011**: The system MUST backfill outdated events (per FR-010) by re-fetching
  their match data through the same incremental per-set approach used for new events,
  following the existing rolling/cyclic backfill process rather than requiring a
  separate one-off migration run.
- **FR-012**: The system MUST retire the existing max_pages-based large-event
  detection used for sets fetching, along with its dependent recovery path (the
  automatic "large event skipped" issue creation and the manually-triggered
  `fetch_large_event` recovery workflow), since incremental per-set fetching and
  cross-run resumption supersede it as the way large events reach completion.
- **FR-013**: The system MUST NOT require any manual trigger or human intervention for
  a large event to reach full completion; reaching completion MUST be possible purely
  through the pipeline's normal scheduled runs, however many are needed.
- **FR-014**: The system MUST NOT re-fetch or re-check an event's full `set_id` list
  against start.gg during normal incremental match-detail fetching (whether the event
  is already complete or still in progress); the placeholders already seeded in
  `matches.json` MUST only be reconciled against start.gg's current set list when that
  event is processed by the existing `event_data_version`-driven backfill cycle.

### Key Entities *(include if feature involves data)*

- **Match Record**: Existing entity, one entry in `matches.json` representing one set
  belonging to an event. Now exists in one of two states: **placeholder** (only
  `set_id` populated; seeded for every set in the event before any detail is fetched)
  or **complete** (full winner/loser, scores, per-game detail; replaces the
  placeholder in place once that set's detail is successfully fetched). There is no
  separate intermediate file — `matches.json` itself, via the mix of placeholder and
  complete records it holds at any point in time, is what tracks the full scope of an
  event's sets and what's still outstanding. The `set_id` field ties every record
  (placeholder or complete) to its start.gg set, enabling per-set tracking,
  deduplication, and resumability.
- **Event**: Existing entity. Its match-data completeness is now determined by whether
  every record in its `matches.json` has moved from placeholder to complete, rather
  than by a single fetch attempt succeeding or failing as a whole.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a large event's fetch is interrupted, 100% of the match records
  successfully retrieved before the interruption are still present in `matches.json`
  afterward (zero data loss on interruption).
- **SC-002**: An event that was previously interrupted reaches full match-data
  completeness after subsequent pipeline runs without re-fetching any set that was
  already recorded.
- **SC-003**: 100% of match records in `matches.json` for events fetched after this
  feature ships can be traced back to a unique source set via the `set_id` field, with
  no duplicate `set_id`s within the same event.
- **SC-004**: The proportion of large events that end up with zero match data due to
  being interrupted mid-fetch drops to 0%, down from the current all-or-nothing
  behavior.
- **SC-005**: Zero large events require a maintainer to manually trigger a separate
  recovery workflow to reach completion; all events, regardless of size, complete
  through the pipeline's normal scheduled runs alone.

## Assumptions

- start.gg's API allows retrieving the list of `set_id`s for an event's sets at a
  lower complexity/page cost than retrieving full set detail (winners, scores, games,
  character selections) for those same sets — this is the basis for splitting
  "list the sets" from "fetch each set's detail," and is the intended fix for the
  complexity-limit failure observed in production.
- Resumption is expected to happen across pipeline runs (e.g., the weekly gap-check
  schedule, or a manual re-run), not necessarily to complete within a single run for
  very large events; incremental progress within a single run is also acceptable where
  time/complexity budget allows.
- This feature changes the *fetching strategy* (per-set retrieval instead of one bulk
  paginated query) and the *storage shape* of `matches.json` (records now pass through
  a placeholder state carrying only `set_id` before being filled in); it does not
  change what data is ultimately captured per completed match beyond adding `set_id`.
- Events that are small enough to already complete in a single pass are unaffected in
  outcome, aside from their match records now also carrying `set_id`.
- Historical `matches.json` records (fetched before this feature) are backfilled with
  `set_id`, not left permanently without it. Outdated events are identified using the
  same version marker the pipeline already uses to detect schema drift, and are
  re-fetched through the existing rolling/cyclic backfill process (the same mechanism
  that currently walks events whose schema version is behind current and refreshes
  them a few at a time) rather than a separate one-off migration script. This also
  means events that were left incomplete by an interrupted fetch — which already show
  up as "outdated" to that process since they're missing `attr.json` — get naturally
  picked up and completed via the incremental per-set approach.
- There is no separate intermediate file for the set_id list: it is represented
  directly inside `matches.json` via placeholder records seeded for every set before
  any detail is fetched, and `matches.json` is already committed to the repository
  under `data/startgg/` like the other event files — so resumption works across
  separate scheduled workflow runs (e.g. consecutive weekly gap-checks) with no new
  file type introduced. Per Constitution Principle I, `docs/data_model.md`'s existing
  `matches.json` schema documentation must still be updated to describe the
  placeholder record shape (a record with only `set_id` populated).
- Existing validation (`scripts/fix/validate_data.py`) discovers event directories by
  finding `attr.json` files (`events_root.rglob("attr.json")`), so an event still
  being incrementally filled in — which, per FR-009, has no `attr.json` yet — is not
  visited by that validator and does not produce false errors from its
  still-placeholder `matches.json`. No change to that discovery mechanism is assumed
  to be necessary for this feature.
- The existing "large-event-skip" GitHub issue + manual `fetch_large_event` workflow
  recovery path is retired by this feature, not kept as a parallel fallback.
  Incremental per-set fetching plus cross-run resumption becomes the sole mechanism by
  which large events reach completion — a large event is no longer a special case that
  needs a human to notice an issue and manually re-run a workflow with a larger page
  limit; it is just an event that takes more scheduled runs than a small one. (A
  pre-existing, independent bug — where the skip report was never written because
  `download_all_tournaments` returned early upon reaching `finish_date`, bypassing the
  report-writing code — was already fixed separately from this feature; that fix is
  now moot for the large-event-skip path specifically, since this feature removes that
  path, but the corrected control flow in `download_all_tournaments` remains in place
  regardless.)
- Fetching an event's `set_id` list (used to seed `matches.json`'s placeholder
  records) remains a paginated query, but is assumed to stay lightweight enough (being
  IDs only, not full set detail) that it does not hit the same page/complexity
  ceilings that motivated the old max_pages safety net. This feature does not define a
  manual escape hatch for the case where even that listing step cannot complete — see
  the corresponding Edge Case.
