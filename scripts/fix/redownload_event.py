#!/usr/bin/env python3
"""Delete and re-download event data by event_id from start.gg.

event_id を指定すると、data/startgg/events 以下から既存のイベントディレクトリを
探し出し（あれば）削除した上で、start.gg から attr.json / matches.json /
seeds.json / standings.json を新規に取得し直す。

git add は一切行わない。競合解消後は自分で git add すること。

使い方:
    # まずは dry-run（削除・取得は行わず、対象を表示するだけ）
    python3 scripts/fix/redownload_event.py --token <TOKEN> --event-id 1642641 1620892

    # 実際に削除して再取得
    python3 scripts/fix/redownload_event.py --token <TOKEN> --event-id 1642641 1620892 --yes
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.fetch.download import (  # noqa: E402
    count_guest_entrants,
    download_all_set,
    download_seeds,
    download_standings,
    extend_user_info,
    load_excluded_event_ids,
    write_event_attributes,
)
from scripts.queries import get_event_details_by_id_query  # noqa: E402
from scripts.utils import (  # noqa: E402
    FetchError,
    NoPhaseError,
    fetch_data_with_retries,
    get_date_parts,
    get_event_directory,
    read_json,
    read_users_jsonl,
    set_api_parameters,
    set_indent_num,
    set_retry_parameters,
)


def count_data_entries(path: Path) -> int:
    """JSON ファイルの {"data": [...]} の要素数を返す。存在しない/壊れている場合は 0。"""
    try:
        return len(read_json(str(path)).get("data", []))
    except (OSError, ValueError):
        return 0


def find_existing_event_dir(events_root: Path, event_id: int) -> Path | None:
    """events_root 以下の attr.json を走査し、event_id が一致するディレクトリを返す。"""
    for attr_path in events_root.rglob("attr.json"):
        try:
            attr = read_json(str(attr_path))
        except (OSError, ValueError):
            continue
        if attr.get("event_id") == event_id:
            return attr_path.parent
    return None


def fetch_event_details(event_id: int) -> tuple[dict, dict]:
    response = fetch_data_with_retries(
        get_event_details_by_id_query(),
        {"eventId": event_id},
    )
    if "data" not in response or response["data"] is None or "event" not in response["data"]:
        raise FetchError(f"Malformed response for event {event_id}: {response}")
    event = response["data"]["event"]
    if event is None:
        raise FetchError(f"Event {event_id} not found.")
    tournament = event.get("tournament")
    if tournament is None:
        raise FetchError(f"Tournament information missing for event {event_id}.")
    return event, tournament


def build_place_dict(tournament: dict) -> dict:
    return {
        "country_code": tournament.get("countryCode"),
        "city": tournament.get("city"),
        "lat": tournament.get("lat"),
        "lng": tournament.get("lng"),
        "venue_name": tournament.get("venueName"),
        "timezone": tournament.get("timezone"),
        "postal_code": tournament.get("postalCode"),
        "venue_address": tournament.get("venueAddress"),
        "maps_place_id": tournament.get("mapsPlaceId"),
    }


def redownload_event(
    event_id: int,
    events_root: Path,
    users: dict,
    users_file_path: str,
    apply: bool,
) -> bool:
    existing_dir = find_existing_event_dir(events_root, event_id)
    if existing_dir is not None:
        print(f"[{event_id}] existing data found: {existing_dir}")
    else:
        print(f"[{event_id}] no existing data found under {events_root}")

    if event_id in load_excluded_event_ids():
        print(f"[{event_id}] excluded: skipping (registered in the exclusion list)")
        return True

    if not apply:
        if existing_dir is not None:
            print(f"[{event_id}] dry-run: would delete {existing_dir} and re-download from start.gg")
        else:
            print(f"[{event_id}] dry-run: would fetch from start.gg and create a new directory under {events_root}")
        return True

    try:
        event, tournament = fetch_event_details(event_id)
    except FetchError as exc:
        print(f"[{event_id}] fetch failed: {exc}", file=sys.stderr)
        return False

    event_name = event.get("name") or "Unknown Event"
    tournament_name = tournament.get("name") or "Unknown Tournament"
    timestamp = event.get("startAt") or tournament.get("startAt")
    if timestamp is None:
        print(f"[{event_id}] no timestamp available from API. Aborting.", file=sys.stderr)
        return False

    if existing_dir is not None:
        event_dir = existing_dir
    else:
        country_code = tournament.get("countryCode") or ""
        year, month, day = get_date_parts(timestamp)
        event_dir = Path(
            get_event_directory(
                str(events_root), country_code, year, month, day, tournament_name, event_name
            )
        )

    before_matches = count_data_entries(event_dir / "matches.json") if existing_dir is not None else 0
    before_standings = count_data_entries(event_dir / "standings.json") if existing_dir is not None else 0

    if existing_dir is not None:
        shutil.rmtree(existing_dir)
        print(f"[{event_id}] deleted {existing_dir}")

    os.makedirs(event_dir, exist_ok=True)

    user_data, player_data, entrant2user = download_standings(event_id, str(event_dir))
    num_entrants = len(user_data)
    try:
        download_seeds(event_id, user_data, player_data, entrant2user, str(event_dir))
    except NoPhaseError as exc:
        print(f"[{event_id}] seeds not available: {exc}", file=sys.stderr)
    extend_user_info(user_data, player_data, users, users_file_path)
    download_all_set(event_id, entrant2user, str(event_dir))

    place = build_place_dict(tournament)
    write_event_attributes(
        num_entrants,
        event_id,
        event_name,
        tournament_name,
        timestamp,
        place,
        tournament.get("url"),
        {},
        event.get("isOnline"),
        str(event_dir),
        guest_entrant_count=count_guest_entrants(user_data),
        end_at=tournament.get("endAt"),
        state=event.get("state"),
        event_type=event.get("type"),
    )
    print(f"[{event_id}] re-downloaded to {event_dir}")

    after_matches = count_data_entries(event_dir / "matches.json")
    after_standings = count_data_entries(event_dir / "standings.json")
    if before_matches > 0 and after_matches == 0:
        print(
            f"\n{'!' * 70}\n"
            f"[WARNING] event_id={event_id}: matches.json had {before_matches} entries before, "
            f"but is now empty after redownload.\n"
            f"This looks like data loss (e.g. the event_id no longer resolves to the same "
            f"tournament on start.gg), not a genuinely empty result. Consider restoring the "
            f"previous data with `git checkout -- \"{event_dir}\"` before committing.\n"
            f"{'!' * 70}\n",
            file=sys.stderr,
        )
    if before_standings > 0 and after_standings == 0:
        print(
            f"\n{'!' * 70}\n"
            f"[WARNING] event_id={event_id}: standings.json had {before_standings} entries before, "
            f"but is now empty after redownload.\n"
            f"This looks like data loss, not a genuinely empty result. Consider restoring the "
            f"previous data with `git checkout -- \"{event_dir}\"` before committing.\n"
            f"{'!' * 70}\n",
            file=sys.stderr,
        )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete and re-download event data by event_id from start.gg."
    )
    parser.add_argument("--token", required=True, help="start.gg API token")
    parser.add_argument("--event-id", type=int, nargs="+", required=True, help="event_id(s) to redownload")
    parser.add_argument("--events-root", default="data/startgg/events", help="Events root directory")
    parser.add_argument("--users-file-path", default="data/startgg/users.jsonl", help="Path to users.jsonl")
    parser.add_argument("--url", default="https://api.start.gg/gql/alpha", help="API URL")
    parser.add_argument("--max-retries", type=int, default=20, help="Maximum number of retries for API requests")
    parser.add_argument("--retry-delay", type=int, default=5, help="Delay between retries in seconds")
    parser.add_argument("--indent-num", type=int, default=2, help="Indentation level for JSON output")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete and re-download. Without this flag, only a dry-run preview is shown.",
    )
    args = parser.parse_args()

    set_indent_num(args.indent_num)
    set_retry_parameters(args.max_retries, args.retry_delay)
    set_api_parameters(args.url, args.token)

    events_root = Path(args.events_root)
    # dry-run はディレクトリの有無を確認するだけなので users.jsonl は読まない。
    users = read_users_jsonl(args.users_file_path) if args.yes else {}

    success = 0
    failure = 0
    for event_id in args.event_id:
        if redownload_event(event_id, events_root, users, args.users_file_path, args.yes):
            success += 1
        else:
            failure += 1

    if not args.yes:
        print("\nDry-run only. Re-run with --yes to actually delete and re-download.")
    print(f"\nDone. success={success} failure={failure}")
    return 0 if failure == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
