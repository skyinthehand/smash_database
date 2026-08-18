#!/usr/bin/env python3
"""tournaments.jsonl に記録済みの各トーナメントについて、start.gg側の現在のイベント
一覧を再取得し、記録済みの event_id 集合に無い新しいイベント(延期時にイベント自体が
作り直された場合など)を検出・取得するツール。

event_id ベースの重複解消(002-incremental-schema-backfill / 004-fix-duplicate-events)
はいずれも同一 event_id の再取得を前提にしており、event_id そのものが作り直される
ケースは検知できない。本スクリプトは tournament_id を起点に、記録済み event_id 集合と
start.gg側の現在の一覧との差分を検出することでこれを補う。「古いイベントが新しい
イベントに置き換わった」という対応関係の判定は行わない(空になったイベントの整理は
scripts/fix/prune_empty_events.py が別途担当する)。

使い方:
    python3 scripts/fetch/backfill_tournament_events.py --token <TOKEN>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.fetch.backfill_schema_version import read_cursor, write_cursor  # noqa: E402
from scripts.fetch.download import (  # noqa: E402
    count_guest_entrants,
    download_all_set,
    download_seeds,
    download_standings,
    extend_user_info,
    fetch_event_ids_from_tournament,
    get_date_parts,
    get_event_directory,
    write_event_attributes,
)
from scripts.queries import get_event_details_by_id_query  # noqa: E402
from scripts.utils import (  # noqa: E402
    FetchError,
    NoPhaseError,
    fetch_data_with_retries,
    read_tournaments_jsonl,
    read_users_jsonl,
    set_api_parameters,
    set_indent_num,
    set_retry_parameters,
    write_jsonl,
)


# ---------------------------------------------------------------------------
# トーナメント一覧・差分検出
# ---------------------------------------------------------------------------

def iter_tournament_ids(tournaments: dict) -> list[int]:
    """tournaments.jsonl に記録済みの全 tournament_id を安定ソート順で返す。
    記録イベント数が0件のトーナメントも含む。"""
    return sorted(tournaments.keys())


def find_new_event_ids(tournament_id: int, game_id: str, recorded_event_ids: set) -> list[int]:
    """start.gg側の現在のイベント一覧のうち、recorded_event_ids に無いものを返す。

    fetch_event_ids_from_tournament() が FetchError を送出した場合(トーナメントが
    見つからない、対象ゲームのイベントが無い等)は空リストを返し、呼び出し元の
    スキャン全体は継続させる。
    """
    try:
        events_info = fetch_event_ids_from_tournament(tournament_id, game_id)
    except FetchError as exc:
        print(f"[{tournament_id}] failed to fetch current event list: {exc}", file=sys.stderr)
        return []
    return [event_id for event_id, _name, _online in events_info if event_id not in recorded_event_ids]


# ---------------------------------------------------------------------------
# 新規イベントの取得・保存(scripts/fix/redownload_event.py と同様のパターン)
# ---------------------------------------------------------------------------

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


def save_new_event(
    tournament_id: int,
    tournament_name: str,
    event_id: int,
    country_code: str,
    startgg_dir: str,
    tournaments: dict,
    users: dict,
    users_file_path: str,
) -> bool:
    """新しい event_id の詳細を取得し、通常の新規イベント取得と同じ手順で保存する。

    成功したら tournaments[tournament_id]["events"] にエントリを追加して True を返す。
    失敗したら例外を送出せず False を返す(呼び出し元は失敗してもスキャンを継続する)。
    """
    try:
        event, tournament = fetch_event_details(event_id)
    except FetchError as exc:
        print(f"[{event_id}] fetch failed: {exc}", file=sys.stderr)
        return False

    event_name = event.get("name") or "Unknown Event"
    resolved_tournament_name = tournament.get("name") or tournament_name
    timestamp = event.get("startAt") or tournament.get("startAt")
    if timestamp is None:
        print(f"[{event_id}] no timestamp available from API. Skipping.", file=sys.stderr)
        return False

    resolved_country_code = tournament.get("countryCode") or country_code
    year, month, day = get_date_parts(timestamp)
    event_dir = get_event_directory(
        startgg_dir, resolved_country_code, year, month, day, resolved_tournament_name, event_name
    )

    user_data, player_data, entrant2user = download_standings(event_id, event_dir)
    num_entrants = len(user_data)
    try:
        download_seeds(event_id, user_data, player_data, entrant2user, event_dir)
    except NoPhaseError as exc:
        print(f"[{event_id}] seeds not available: {exc}", file=sys.stderr)
    extend_user_info(user_data, player_data, users, users_file_path)
    download_all_set(event_id, entrant2user, event_dir)

    place = build_place_dict(tournament)
    write_event_attributes(
        num_entrants,
        event_id,
        event_name,
        resolved_tournament_name,
        timestamp,
        place,
        tournament.get("url"),
        {},
        event.get("isOnline"),
        event_dir,
        guest_entrant_count=count_guest_entrants(user_data),
        end_at=tournament.get("endAt"),
    )

    tournaments[tournament_id]["events"].append({
        "event_id": event_id,
        "event_name": event_name,
        "path": event_dir,
    })
    print(f"[{tournament_id}] new event {event_id} ({event_name}) saved to {event_dir}")
    return True


# ---------------------------------------------------------------------------
# 循環スキャン本体
# ---------------------------------------------------------------------------

def run_tournament_event_sync(
    tournament_file_path: str,
    cursor_path: Path,
    startgg_dir: str,
    users_file_path: str,
    game_id: str,
    max_tournaments: int,
) -> dict:
    """1回の実行分のトーナメント単位スキャンを行い、サマリーを dict で返す。

    {"tournaments_checked": int, "new_events_found": int, "wrapped_around": bool}
    """
    tournaments = read_tournaments_jsonl(tournament_file_path)
    tournament_ids = iter_tournament_ids(tournaments)
    total = len(tournament_ids)
    if total == 0:
        return {"tournaments_checked": 0, "new_events_found": 0, "wrapped_around": False}

    id_strs = [str(t) for t in tournament_ids]
    cursor_value = read_cursor(cursor_path)
    start_index = 0
    if cursor_value is not None and cursor_value in id_strs:
        start_index = (id_strs.index(cursor_value) + 1) % total

    users = read_users_jsonl(users_file_path)

    checked = 0
    new_events_found = 0
    wrapped_around = False
    last_index = None

    for offset in range(total):
        if max_tournaments > 0 and checked >= max_tournaments:
            break
        index = (start_index + offset) % total
        if index < start_index:
            wrapped_around = True
        tournament_id = tournament_ids[index]
        tournament_entry = tournaments[tournament_id]
        recorded_event_ids = {e.get("event_id") for e in tournament_entry.get("events", [])}

        new_event_ids = find_new_event_ids(tournament_id, game_id, recorded_event_ids)
        for event_id in new_event_ids:
            if save_new_event(
                tournament_id, tournament_entry.get("name") or "Unknown Tournament", event_id,
                "", startgg_dir, tournaments, users, users_file_path,
            ):
                new_events_found += 1

        checked += 1
        last_index = index

    if last_index is not None:
        write_cursor(cursor_path, id_strs[last_index])

    if new_events_found > 0:
        write_jsonl(list(tournaments.values()), tournament_file_path, with_version=True)

    return {
        "tournaments_checked": checked,
        "new_events_found": new_events_found,
        "wrapped_around": wrapped_around,
    }


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect and fetch newly (re)created events for known tournaments in tournaments.jsonl."
    )
    parser.add_argument("--token", required=True, help="start.gg API token")
    parser.add_argument("--tournament_file_path", default="data/startgg/tournaments.jsonl", help="Path to tournaments.jsonl")
    parser.add_argument(
        "--cursor_path",
        default="data/startgg/tournament_event_sync_cursor.txt",
        help="Path to store and read the tournament scan cursor.",
    )
    parser.add_argument("--events_root", default="data/startgg/events", help="Events root directory")
    parser.add_argument("--users_file_path", default="data/startgg/users.jsonl", help="Path to users.jsonl")
    parser.add_argument("--game_id", default="1386", help="Game ID used to filter each tournament's events.")
    parser.add_argument(
        "--max_tournaments",
        type=int,
        default=200,
        help="Maximum number of tournaments to check in a single run (0 means unlimited).",
    )
    parser.add_argument("--url", default="https://api.start.gg/gql/alpha", help="API URL")
    parser.add_argument("--max_retries", type=int, default=20, help="Maximum number of retries for API requests")
    parser.add_argument("--retry_delay", type=int, default=5, help="Delay between retries in seconds")
    parser.add_argument("--indent_num", type=int, default=2, help="Indentation level for JSON output")
    args = parser.parse_args()

    set_indent_num(args.indent_num)
    set_retry_parameters(args.max_retries, args.retry_delay)
    set_api_parameters(args.url, args.token)

    cursor_path = Path(args.cursor_path)

    print(f"Cursor: {read_cursor(cursor_path) or '(none, starting from the beginning)'}")

    summary = run_tournament_event_sync(
        args.tournament_file_path, cursor_path, args.events_root, args.users_file_path,
        args.game_id, args.max_tournaments,
    )

    print(
        f"Done. tournaments_checked={summary['tournaments_checked']} "
        f"new_events_found={summary['new_events_found']} "
        f"wrapped_around={str(summary['wrapped_around']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
