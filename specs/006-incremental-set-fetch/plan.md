# Implementation Plan: Incremental Per-Set Match Fetching & Recovery

**Branch**: `006-incremental-set-fetch` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-incremental-set-fetch/spec.md`

## Summary

Large start.gg events (hundreds of entrants, thousands of sets) currently fail to save
any match data at all when the single bulk, paginated `event.sets` query exceeds the
page/complexity budget — `matches.json` and `attr.json` never get written, even though
`standings.json`/`seeds.json` already succeeded. The fix replaces that one-shot bulk
fetch with an incremental, resumable approach: seed `matches.json` with one placeholder
record (`set_id` only) per set — via a new lightweight, ID-only `event.sets` query —
before fetching any full detail, then fetch each outstanding set's full detail directly
by ID (`set(id: ID!)`, confirmed to exist on start.gg's API) and replace its placeholder
in place. This keeps each request's complexity bounded regardless of event size, lets
partially-fetched events survive interruption and resume across scheduled runs, and
lets `matches.json` itself (mix of placeholder vs. complete records) double as the
outstanding-work tracker — no separate intermediate file. It also retires the
now-unnecessary max_pages-based large-event-skip issue/`fetch_large_event` manual
recovery path (FR-012/013), and backfills `set_id` onto historical `matches.json`
records via the existing `event_data_version`-driven rolling backfill cycle (FR-010/011).

## Technical Context

**Language/Version**: Python 3.11 (matches CI in `.github/workflows/*.yml`)

**Primary Dependencies**: `requests` (only third-party dependency); everything else is
stdlib (`json`, `argparse`, `os`, `time`, `unittest`). No web framework, no ORM, no
package manager config file (`pip install requests` directly in CI).

**Storage**: Flat JSON files under `data/startgg/events/{Region}/{YYYY}/{MM}/{DD}/
{Tournament}/{Event}/{attr,standings,seeds,matches}.json`, committed directly to the
git repository (no database). `matches.json` gains a placeholder record shape as part
of this feature; no new file is introduced.

**Testing**: `python -m unittest scripts.test.<module>` (stdlib `unittest`,
`unittest.mock.patch` for GraphQL/API mocking — see `scripts/test/test_download.py`
for the established pattern of mocking `fetch_latest_tournaments_by_game`,
`fetch_event_ids_from_tournament`, `download_all_set`, etc.). Constitution Principle
III requires `scripts.test.test_validate_data` to keep passing and requires new tests
for any new data shape.

**Target Platform**: GitHub Actions (`ubuntu-latest`, 60-minute job timeout per
`.github/workflows/data_gap_check.yml`) for scheduled runs, plus local CLI execution
for manual/ad-hoc runs (`scripts/fetch/download.py`, `download_specific_event.py`,
`backfill_schema_version.py`).

**Project Type**: CLI / batch data pipeline (no server, no UI). Single-project layout
under `scripts/` (see Project Structure below).

**Performance Goals**: Not latency-sensitive. The binding constraint is the GitHub
Actions job timeout (60 min) combined with start.gg's per-request GraphQL complexity
limit — the design goal is that no single request's complexity scales with an event's
total set count, so progress is never all-or-nothing.

**Constraints**: Constitution Principle V — all new start.gg API calls MUST go through
`scripts/utils.py`'s `fetch_data_with_retries()` (single request) / `fetch_all_nodes()`
(paginated) rather than hand-rolled retry/backoff. Constitution Principle II — must
stay idempotent/incremental; re-running against an event with existing placeholder and
complete records must not re-fetch already-complete sets or duplicate records.
Constitution Principle I — the `matches.json` schema change requires an
`EVENT_DATA_VERSION` bump, a `docs/data_model.md` update in the same PR, and a backfill
path for existing data (reusing `scripts/fetch/backfill_schema_version.py`'s rolling
cycle, not a one-off migration).

**Scale/Scope**: `data/startgg/events/` currently holds several thousand event
directories. Large events observed in production: `grand_slum` (488 entrants,
`total_pages=1267` at `max_pages=200`) and `SHIBUYA_DAIRAN` (256 entrants,
`total_pages=510`) — see spec.md User Story 1. The weekly gap-check
(`data_gap_check.yml`) scans a rolling 60-day window; other workflows
(`schema_backfill.yml`, `data_backfill.yml`, `update_tournament.yml`) run on their own
schedules against the full history.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. データスキーマの整合性とバージョニング | `matches.json` gets a new placeholder record shape → `EVENT_DATA_VERSION` bump (5→6), `docs/data_model.md` updated same PR, existing data migrated via the *existing* `backfill_schema_version.py` rolling cycle (FR-010/011), not a bespoke migration script. | PASS (design commits to this) |
| II. 冪等でインクリメンタルな収集 | Re-running fetch for an event with a mix of placeholder/complete records only re-fetches placeholders (FR-006/007/008); `done.csv`/`tournament_events_complete()` already treat an event without `attr.json` as incomplete, so in-progress large events keep getting revisited naturally — no new "done" tracking needed. | PASS |
| III. マージ前の検証ゲート | New tests required in `scripts/test/` for: placeholder seeding, outstanding-set detection, no-duplicate-set_id, completion-gates-on-no-placeholders, large-event-skip removal. `scripts.test.test_validate_data` must keep passing (see Phase 1 note on `validate_data.py`). | PASS (planned as tasks) |
| IV. ブランチとオートメーションの規律 | No change to the direct-to-`main` / concurrency-group / rebase-retry commit pattern used by `data_gap_check.yml` and friends; this feature does not introduce new automation, it changes what `download.py` does within the existing workflows. Removing `fetch_large_event.yml` is a deletion, not a new automation path. | PASS |
| V. 外部APIへの耐障害アクセス | New queries (event set-ID listing, single/batched `set(id:)` detail fetch) MUST go through `fetch_all_nodes()` / `fetch_data_with_retries()` respectively — no custom retry loop. Verified `set(id: ID!): Set` exists on start.gg's schema (see research.md). | PASS (design commits to this) |
| データ保存規約 | Directory layout (`{Region}/{YYYY}/{MM}/{DD}/{Tournament}/{Event}`) unchanged. The "no manual escape hatch" residual risk (spec.md Edge Cases) gets recorded in `docs/fix.md` per convention, not left as a code comment. | PASS (planned as task) |
| 開発ワークフロー | Changes live in `scripts/fetch/download.py` (fetch logic) and `scripts/queries.py` (new queries) — same files/roles as today, no new script category. `docs/data_model.md`, `docs/startgg_design.md`, `docs/flow.md`, `docs/fix.md` updates travel in the same PR as the schema/workflow change. | PASS (planned as tasks) |

No violations requiring justification — Complexity Tracking table is empty.

**Post-design re-check** (after Phase 0/1, see research.md, data-model.md,
contracts/, quickstart.md): No new violations introduced. Every commitment the table
above made — reusing `fetch_all_nodes()`/`fetch_data_with_retries()` (Principle V,
confirmed against start.gg's actual schema in research.md §2), routing schema change
through `EVENT_DATA_VERSION` + the existing `backfill_schema_version.py` cycle
(Principle I, research.md §5), keeping `matches.json` the single source of truth so no
new "done" tracking is needed (Principle II), and recording the residual manual-escape-
hatch risk in `docs/fix.md` rather than a code comment (data storage conventions) — is
carried through consistently into the Phase 1 design artifacts. Still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/006-incremental-set-fetch/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── matches-record-contract.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

This is the existing repository layout; no new top-level directories are introduced.
Changes land inside the existing `fetch`/`fix`/`test` split (Constitution "開発ワークフロー").

```text
scripts/
├── fetch/
│   ├── download.py                 # MODIFIED: placeholder seeding + per-set incremental
│   │                                #   fetch replace existing bulk download_all_set() path;
│   │                                #   FR-012/013 removes max_pages large-event-skip logic
│   ├── backfill_schema_version.py  # MODIFIED (or unaffected if it fully delegates to
│   │                                #   download.py functions): rolling backfill picks up
│   │                                #   set_id-less events via EVENT_DATA_VERSION bump
│   ├── download_specific_event.py  # reviewed for consistency, MODIFIED only if it
│   │                                #   duplicates the old bulk-fetch pattern
│   └── refresh_event_dir.py        # reviewed for consistency (matches_only path)
├── fix/
│   └── validate_data.py            # reviewed; optionally strengthened to assert no
│                                    #   placeholder records remain once attr.json exists
├── test/
│   ├── test_download.py            # MODIFIED: new tests for FR-001–FR-009, FR-014
│   └── test_validate_data.py       # MUST keep passing (Constitution Principle III)
├── queries.py                      # MODIFIED: add lightweight event.sets ID-only query
│                                    #   and set(id:) single/batched detail query
└── utils.py                        # MODIFIED: EVENT_DATA_VERSION bump (5 → 6)

.github/workflows/
├── data_gap_check.yml              # UNCHANGED (behavior improves as a side effect of
│                                    #   download.py's new fetch strategy)
└── fetch_large_event.yml           # REMOVED (FR-012)

docs/
├── data_model.md                   # MODIFIED: document matches.json placeholder shape,
│                                    #   set_id field, EVENT_DATA_VERSION=6
├── startgg_design.md               # MODIFIED: document the two new queries
├── flow.md                         # MODIFIED if the large-event-skip step is depicted
└── fix.md                          # MODIFIED: record the "no manual escape hatch for
                                     #   set-ID-listing overflow" residual risk

data/startgg/events/{Region}/{YYYY}/{MM}/{DD}/{Tournament}/{Event}/
├── attr.json        # UNCHANGED shape; now only written once no placeholders remain
├── standings.json    # UNCHANGED
├── seeds.json        # UNCHANGED
└── matches.json      # MODIFIED shape: records may be placeholder (set_id only) or
                       #   complete; set_id added to every record
```

**Structure Decision**: Single existing Python script project (`scripts/fetch`,
`scripts/fix`, `scripts/test`, `scripts/queries.py`, `scripts/utils.py`) — no new
project, package, or top-level directory. This feature is implemented as changes to
`download.py`'s fetch strategy plus two new GraphQL queries in `queries.py`, following
the same fetch/fix/test separation the constitution already mandates.

## Complexity Tracking

> No Constitution Check violations — this table is intentionally empty.
