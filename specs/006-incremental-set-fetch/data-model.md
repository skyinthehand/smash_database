# Data Model: Incremental Per-Set Match Fetching & Recovery

This feature changes one existing file's schema (`matches.json`) and one shared
version constant (`EVENT_DATA_VERSION`). It introduces no new files. The full
persisted-file schema documentation lives in `docs/data_model.md` (to be updated as
part of implementation, per Constitution Principle I); this document describes the
entities and their lifecycle for design purposes.

## Entity: Match Record

One entry in `matches.json`'s `data` array. Represents one start.gg set belonging to
an event. Exists in exactly one of two states at any point in time.

### State: `placeholder`

| Field | Type | Notes |
|---|---|---|
| `set_id` | integer | start.gg set ID. The only field present. |

No other keys are present on a placeholder record (see research.md §4 for why
key-presence, not a `null` value, distinguishes this state).

### State: `complete`

| Field | Type | Notes |
|---|---|---|
| `set_id` | integer | **New in this feature.** start.gg set ID; unchanged from the placeholder that was replaced. |
| `winner_id` | integer \| null | Existing field. `null` for unlinked/guest entrants. |
| `loser_id` | integer \| null | Existing field. |
| `winner_score` | integer | Existing field. |
| `loser_score` | integer | Existing field. |
| `round_text` | string \| null | Existing field. |
| `round` | integer \| null | Existing field. |
| `phase` | string \| null | Existing field. |
| `phase_order` | integer \| null | Existing field. |
| `wave` | string \| null | Existing field. |
| `dq` | boolean | Existing field. |
| `cancel` | boolean | Existing field. |
| `state` | integer | Existing field (start.gg set state). |
| `details` | array | Existing field; per-game detail (`game_id`, `order_num`, `winner_id`, scores, `stage`, `selections`). |

### State transitions

```
(does not exist) --[event set-ID listing fetched]--> placeholder
placeholder       --[set detail fetch succeeds]-----> complete
placeholder       --[set detail fetch fails]--------> placeholder (unchanged, retried later)
complete          --[re-fetch, e.g. version backfill]-> complete (overwritten in place, same set_id)
```

A record MUST NOT transition from `complete` back to `placeholder`. A record's
`set_id` MUST NOT change across a transition (FR-004, FR-008). There is exactly one
record per `set_id` per event at all times (FR-008) — a fetch never appends a second
record for a `set_id` that already has one, whether placeholder or complete.

### Validation rules (derived from spec.md Functional Requirements)

- FR-002/FR-007: Every `set_id` known for an event (from the ID-listing fetch) MUST
  have exactly one corresponding record (placeholder or complete) in `matches.json`.
- FR-008: No two records in the same event's `matches.json` share a `set_id`.
- FR-009: An event is "complete" (eligible for `attr.json` with
  `archive_status: "completed"`) iff every record in its `matches.json` is in the
  `complete` state (or is covered by the pre-existing `excluded_phases.json`
  exclusion mechanism, unchanged by this feature).

## Entity: Event (existing, behavior change only)

No new fields. Behavior change: `attr.json`'s existence is now gated on "no
placeholder Match Records remain" (state, not a single fetch attempt's success),
per FR-009. Everything else about `attr.json` (`docs/data_model.md`'s existing
schema) is unchanged by this feature, aside from the `event_data_version` bump.

## Shared constant: `EVENT_DATA_VERSION`

`scripts/utils.py`: `5 → 6`. Signals that `matches.json` records for this event
schema generation carry `set_id` and may (transiently, pre-completion) include
placeholder records. Drives `scripts/fetch/backfill_schema_version.py`'s existing
rolling backfill of events at older versions (research.md §5) — no schema-specific
change needed inside that scanner itself, since it already generically compares
`attr.json`'s `event_data_version` (or `0` if `attr.json` is absent) against the
current constant.

## Relationships

```
Event (1) ── has ── Match Record (0..N)   [N = event's total set count]
Match Record ── belongs to exactly one ── start.gg Set (by set_id)
```

No relationship changes; `matches.json` continues to be the sole place Match Records
are stored, and continues to live at the same path as today
(`data/startgg/events/{Region}/{YYYY}/{MM}/{DD}/{Tournament}/{Event}/matches.json`).
