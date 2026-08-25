# Quickstart: Validating Incremental Per-Set Match Fetching & Recovery

This guide validates the feature end-to-end once implemented. See
[data-model.md](./data-model.md) for record shapes and
[contracts/matches-record-contract.md](./contracts/matches-record-contract.md) for the
guarantees being checked.

## Prerequisites

- Python 3.11, `pip install requests` (repo has no other dependencies).
- A start.gg API token (`STARTGG_TOKEN`) with read access, for the optional live-API
  scenarios below. The unit-test scenarios need no token (all GraphQL calls are
  mocked, per the existing pattern in `scripts/test/test_download.py`).
- Run all commands from the repository root.

## 1. Unit tests (fast, no network — run this first)

```bash
python -m unittest scripts.test.test_download -v
python -m unittest scripts.test.test_validate_data -v
python -m unittest scripts.test.test_backfill_schema_version -v
```

Expected: all pass. This is the Constitution Principle III gate and should cover, at
minimum:

- `matches.json` is seeded with one placeholder (`set_id`-only) record per known set
  before any per-set detail fetch (FR-002).
- A subsequent run against an event with a mix of placeholder/complete records fetches
  detail only for the still-placeholder `set_id`s (FR-006/FR-007) and never appends a
  duplicate record for a `set_id` that already has one (FR-008).
- `attr.json` is written (with `archive_status: "completed"`) only once no placeholder
  records remain (FR-009).
- No code path can raise `MaxPagesExceededError` from set/match detail fetching
  anymore, and no `large-event-skip`-labeled artifact is produced (FR-012/FR-013).
- `backfill_schema_version.py` picks up an event whose `attr.json.event_data_version`
  is below the new `EVENT_DATA_VERSION` (or whose `attr.json` is entirely absent) and
  re-fetches it through the incremental path (FR-010/FR-011).

## 2. Live-API scenario: interrupted fetch survives (User Story 1)

Requires `STARTGG_TOKEN`. Pick a large real tournament (or reuse the ones already
identified during this feature's investigation: `第１９回グランドスラム` /
`渋谷大乱 第一陣` — see spec.md User Story 1) and its `tournament_id`.

```bash
python scripts/fetch/download.py --token "$STARTGG_TOKEN" \
  --tournament_ids <TOURNAMENT_ID> --country_code JP
# let it run for a short while, then interrupt it (Ctrl-C) partway through the
# per-set detail fetch phase for the large event
```

**Check** (User Story 1 / SC-001):

```bash
python3 -c "
import json
d = json.load(open('<event_dir>/matches.json'))
placeholders = [r for r in d['data'] if 'winner_id' not in r]
complete = [r for r in d['data'] if 'winner_id' in r]
print(f'placeholders={len(placeholders)} complete={len(complete)}')
assert not any(r for r in d['data'] if 'set_id' not in r), 'every record must carry set_id'
"
ls <event_dir>/attr.json  # MUST NOT exist yet — event is still incomplete
```

Re-run the same `download.py` command. **Check** (User Story 1 / FR-006, SC-002): the
`complete` count only grows, previously-complete records are byte-for-byte unchanged,
and no `set_id` appears more than once. Repeat until `attr.json` appears — this proves
completion is reachable purely by re-running the normal command, with no manual
workflow (User Story 2 / SC-005).

## 3. Traceability check (User Story 4)

```bash
python3 -c "
import json
d = json.load(open('<event_dir>/matches.json'))
set_ids = [r['set_id'] for r in d['data']]
assert len(set_ids) == len(set(set_ids)), 'duplicate set_id found'
print(f'{len(set_ids)} unique set_id values, all present')
"
```

## 4. Backfill check (FR-010/FR-011)

Against a small, already-committed pre-feature event directory (any event with
`attr.json.event_data_version` < the new value):

```bash
python scripts/fetch/backfill_schema_version.py --token "$STARTGG_TOKEN" --max_events 1
```

**Check**: the event's `attr.json.event_data_version` is now current, and its
`matches.json` records all carry `set_id` with no placeholders left behind.

## 5. Retirement check (FR-012/FR-013)

```bash
test ! -f .github/workflows/fetch_large_event.yml && echo "removed: OK"
grep -L "large-event-skip" .github/workflows/data_gap_check.yml && echo "no large-event-skip step: OK"
```

## 6. Documentation sync (Constitution Principle I)

Confirm `docs/data_model.md` documents the placeholder record shape and the new
`EVENT_DATA_VERSION`, and `docs/fix.md` records the residual "no manual escape hatch
if set-ID listing itself can't complete" risk (spec.md Edge Cases).
