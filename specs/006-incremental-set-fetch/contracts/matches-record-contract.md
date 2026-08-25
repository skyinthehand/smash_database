# Contract: `matches.json` Record Shape

This project has no network API or CLI surface exposed to external users — its
"interface" is the JSON files it writes under `data/startgg/`, consumed by other
scripts in this repository (`scripts/fix/validate_data.py`, `scripts/queries.py`,
`scripts/fetch/backfill_schema_version.py`) and, per `docs/data_model.md`, by anyone
reading the committed data directly. This document is the contract for the one file
shape this feature changes.

## Producer

`scripts/fetch/download.py` (all entry points that write `matches.json`: the main
`download_all_tournaments()` path, `download_specific_event.py`,
`backfill_schema_version.py`'s re-fetch path).

## Consumers

- `scripts/fix/validate_data.py` — reads `matches.json` for events it discovers via
  `attr.json` presence (see research.md §7). MUST continue to see only fully-`complete`
  records for any event whose `attr.json` exists, per FR-009 — this is the invariant
  that keeps the existing validator correct without modification.
- `scripts/queries.py` and any other read-only analysis code — same invariant: an
  event is only ever exposed as "done" (via `attr.json`/`archive_status`) once its
  `matches.json` contains no placeholder records.
- `scripts/fetch/backfill_schema_version.py` — both a producer (re-fetches outdated
  events) and, transitively, a consumer of the placeholder/complete state to decide
  what remains outstanding for a partially-backfilled event.

## Guarantees this feature MUST uphold

1. **No consumer that gates on `attr.json` ever observes a placeholder record.**
   `attr.json` (with `archive_status: "completed"`) is written if and only if every
   record in that event's `matches.json` is `complete` (FR-009). A consumer that reads
   `matches.json` without checking for `attr.json` first has always had to tolerate an
   event's data being absent/incomplete (interruption was already possible before this
   feature); this feature does not change that pre-existing expectation, it just gives
   "incomplete" a more granular in-file representation instead of a missing file.

2. **`set_id` uniqueness.** Within one event's `matches.json`, no two records share a
   `set_id`, in either state (FR-008). Consumers may safely key on `set_id`.

3. **Monotonic state transitions.** A record only ever moves `placeholder → complete`,
   never the reverse, and its `set_id` is invariant across that transition (data-model.md).

4. **Backward-compatible complete-record shape.** The `complete` state is the existing
   pre-feature `matches.json` record shape (`winner_id`, `loser_id`, `winner_score`,
   `loser_score`, `round_text`, `round`, `phase`, `phase_order`, `wave`, `dq`, `cancel`,
   `state`, `details`) plus the new `set_id` field. No existing field is renamed,
   retyped, or removed — consumers written against the pre-feature shape continue to
   work against `complete` records unchanged, aside from gaining `set_id`.

## Non-guarantees (explicitly out of scope)

- Placeholder records are **not** guaranteed to ever appear in a `matches.json` a
  consumer reads, if that consumer only ever looks at events gated by `attr.json`
  (which is the existing, expected usage pattern per guarantee #1).
- This contract does not cover `standings.json`, `seeds.json`, or `attr.json` — those
  are unchanged by this feature.
