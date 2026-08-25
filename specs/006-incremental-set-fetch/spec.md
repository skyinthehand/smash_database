# Feature Specification: Incremental Per-Set Match Fetching & Recovery

**Feature Branch**: `006-incremental-set-fetch`

**Created**: 2026-08-25

**Status**: Draft

**Input**: User description: "途中で打ち切られた場合に結局データが保存されないのは困ります。complexityが高すぎるのが原因だったと思いますが、であれば中間ファイルとしてset_idだけ保存しておいて、setごとに後から埋めていく方式にしたい。matches.jsonにset_id（snake_caseでいいっけ？）も保存していくようにしたい。"

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
   event (tracked via its Event Set List and resumed on subsequent runs) rather than
   being specially flagged for manual intervention.

---

### User Story 3 - Track which sets remain to be fetched (Priority: P3)

As the maintainer, I want an intermediate record of the set IDs that belong to an
event, saved separately from (and before) the full match details, so that the pipeline
(and I, when investigating) can tell which sets are still outstanding for an event at
any point.

**Why this priority**: This is the mechanism that makes User Story 1's recovery
possible — without knowing the full expected set of `set_id`s up front, the pipeline
cannot tell "outstanding" apart from "this event legitimately has no more sets."

**Independent Test**: Can be fully tested by fetching only the set ID list for an
event (without fetching full set details) and confirming the list is persisted and
matches the number of sets start.gg reports for that event.

**Acceptance Scenarios**:

1. **Given** an event that has not yet been fetched, **When** the pipeline begins
   processing it, **Then** the full list of the event's `set_id`s is saved before any
   per-set match detail is fetched.
2. **Given** an event with a saved set ID list and a partially filled `matches.json`,
   **When** the outstanding sets are computed, **Then** the result is exactly the
   `set_id`s present in the list but absent from `matches.json`.

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

- What happens when start.gg's set list for an event changes between the first save of
  the intermediate set ID list and a later resumption (e.g., a set is added, removed,
  or replaced after a TO edits the bracket)?
- What happens when the per-set detail fetch fails for an individual `set_id` (e.g. a
  transient API error) after the set ID list has already been saved — does only that
  set get retried on the next run, leaving other already-fetched sets untouched?
- What happens when an event's set-detail fetch completes fully in one run with no
  interruption — is the intermediate set ID list still produced, and if so, what
  happens to it once the event is complete?
- How does the pipeline decide an event's match data is "complete" now that matches can
  arrive incrementally across multiple runs, given `attr.json` (which marks
  `archive_status: "completed"`) is currently only written after a single all-or-nothing
  fetch succeeds?
- What happens if the same `set_id` is fetched twice (e.g. due to a retry racing with a
  resumed run) — must the resulting `matches.json` still contain exactly one record for
  that set?
- What happens if even fetching an event's `set_id` list (the one remaining paginated
  query in this design) cannot complete for a pathologically large event? Since the
  existing max_pages-based safety net (large-event-skip issue + manual
  `fetch_large_event` workflow) is being retired rather than kept as a narrower
  fallback, such an event has no dedicated manual escape hatch under this feature — it
  relies on incremental per-set fetching and repeated scheduled runs to eventually
  converge, same as any other event.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST obtain the full list of `set_id`s belonging to an event
  as its own step, separate from fetching each set's full match detail (winner/loser,
  scores, games, character selections).
- **FR-002**: The system MUST persist an event's set ID list, as part of that event's
  saved data alongside its other files, before attempting to fetch any per-set match
  detail for that event — so the set of "sets to fetch" is known even if detail
  fetching is interrupted, and remains known across separate, later pipeline runs (not
  only within the run that first fetched the list).
- **FR-003**: The system MUST fetch full match detail for an event's sets incrementally
  (one set, or a small batch of sets, at a time) and write each successfully fetched
  set's match record into `matches.json` as it completes, rather than only after every
  set in the event has succeeded.
- **FR-004**: Every match record in `matches.json` MUST include a `set_id` field
  (snake_case, consistent with this file's existing field naming) identifying the
  start.gg set the record was derived from.
- **FR-005**: When fetching is interrupted partway through an event's sets (for any
  reason — complexity/page limit reached, process stopped, transient failure), the
  system MUST retain the match records already successfully fetched and written for
  that event rather than discarding them.
- **FR-006**: When the pipeline processes an event that already has some match records
  saved, it MUST fetch only the `set_id`s that are in the event's saved set ID list but
  not yet present in `matches.json`, and MUST NOT re-fetch sets already recorded.
- **FR-007**: The system MUST be able to determine, for a given event, which `set_id`s
  remain outstanding by comparing the persisted set ID list against the `set_id`s
  already present in `matches.json`.
- **FR-008**: The system MUST NOT produce more than one match record for the same
  `set_id` within an event's `matches.json`, including when a fetch is retried or
  resumed.
- **FR-009**: The system MUST only consider an event's match data complete — and only
  then proceed to write `attr.json` with `archive_status: "completed"` — once every
  `set_id` in the event's saved set ID list has a corresponding match record (or has
  been explicitly determined to be excluded, per existing exclusion handling).
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

### Key Entities *(include if feature involves data)*

- **Event Set List (intermediate record)**: The set of `set_id`s that belong to a given
  event, captured up front for that event before any match detail is fetched. Saved
  alongside the event's other data files (`attr.json`, `standings.json`, `seeds.json`,
  `matches.json`) so it survives between separate pipeline runs, not just within one
  run. Used to know the full scope of work for the event and to compute which sets
  remain outstanding.
- **Match Record**: Existing entity representing one completed set's result
  (winner/loser, scores, per-game detail). Gains a `set_id` attribute identifying the
  start.gg set it came from, enabling per-set tracking, deduplication, and resumability.
- **Event**: Existing entity. Its match-data completeness is now determined by full
  coverage of its Event Set List rather than by a single fetch attempt succeeding or
  failing as a whole.

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
  paginated query) and the *storage shape* (`set_id` on match records); it does not
  change what per-match data is captured beyond adding `set_id`.
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
- The per-event set ID list (the intermediate record in "Key Entities") is committed
  to the repository under `data/startgg/`, alongside the event's other files, so
  resumption works across separate scheduled workflow runs (e.g. consecutive weekly
  gap-checks), not only within a single run. Per Constitution Principle I, this means
  the new file's shape must be documented in `docs/data_model.md` and carry a
  `version` field like the other event files.
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
- Fetching an event's `set_id` list remains a paginated query, but is assumed to stay
  lightweight enough (being IDs only, not full set detail) that it does not hit the
  same page/complexity ceilings that motivated the old max_pages safety net. This
  feature does not define a manual escape hatch for the case where even that listing
  step cannot complete — see the corresponding Edge Case.
