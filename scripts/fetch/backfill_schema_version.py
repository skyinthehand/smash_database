#!/usr/bin/env python3
"""既存イベントの attr.json に保存された event_data_version が現在の
scripts.utils.EVENT_DATA_VERSION より古いものを、安定ソート順の循環スキャンで
少しずつ再取得し、最新のスキーマへ収束させるツール。

data/startgg/events 以下のイベントディレクトリをパス文字列の昇順で列挙し、
カーソルファイル(--cursor_path)に保存された「直近に確認したディレクトリ」の
次から走査を再開する。1回の実行で実際に再取得する件数は --max_events で
上限を設定できる。既に最新バージョンのイベントは API を呼ばずスキップする。

使い方:
    python3 scripts/fetch/backfill_schema_version.py --token <TOKEN>
"""

from __future__ import annotations

import argparse
import os
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
    write_event_attributes,
)
from scripts.queries import get_event_details_by_id_query  # noqa: E402
from scripts.utils import (  # noqa: E402
    EVENT_DATA_VERSION,
    FetchError,
    NoPhaseError,
    fetch_data_with_retries,
    read_json,
    read_tournaments_jsonl,
    read_users_jsonl,
    set_api_parameters,
    set_indent_num,
    set_retry_parameters,
)


# ---------------------------------------------------------------------------
# ディレクトリ走査・バージョン判定
# ---------------------------------------------------------------------------

def iter_event_dirs(events_root: Path) -> list[Path]:
    """events_root 以下の、attr.json または standings.json を持つディレクトリ
    (=取得が試みられたイベントディレクトリ)を、Japanリージョンを優先しつつ
    パス文字列の昇順(安定ソート)で返す。standings.json はパイプライン中で
    最初に書き込まれるファイルのため、attr.json 単独では発見できない(取得が
    途中で打ち切られた)ディレクトリも、standings.json 経由で網羅的に発見できる。"""

    def sort_key(event_dir: Path) -> tuple[int, str]:
        try:
            region = event_dir.relative_to(events_root).parts[0]
        except (ValueError, IndexError):
            region = ""
        is_not_japan = 0 if region == "Japan" else 1
        return (is_not_japan, str(event_dir))

    candidates = {p.parent for p in events_root.rglob("attr.json")}
    candidates.update(p.parent for p in events_root.rglob("standings.json"))
    return sorted(candidates, key=sort_key)


def read_event_data_version(event_dir: Path) -> int:
    """attr.json の event_data_version を返す。存在しない/壊れている場合は 0。"""
    try:
        attr = read_json(str(event_dir / "attr.json"))
    except (OSError, ValueError):
        return 0
    return attr.get("event_data_version") or 0


# ---------------------------------------------------------------------------
# カーソル永続化
# ---------------------------------------------------------------------------

def read_cursor(cursor_path: Path) -> str | None:
    if not cursor_path.exists():
        return None
    text = cursor_path.read_text(encoding="utf-8").strip()
    return text or None


def write_cursor(cursor_path: Path, path_str: str) -> None:
    if cursor_path.parent != Path(""):
        cursor_path.parent.mkdir(parents=True, exist_ok=True)
    cursor_path.write_text(path_str + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 1イベント分の再取得(scripts/fix/redownload_event.py と同様のパターン)
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


def _find_event_id_in_tournaments(tournaments: dict | None, event_dir: Path) -> int | None:
    """tournaments.jsonl の記録から、event_dir に一致する event_id を探す。"""
    if not tournaments:
        return None
    target = str(event_dir)
    for tournament in tournaments.values():
        for event in tournament.get("events", []):
            if event.get("path") == target:
                return event.get("event_id")
    return None


def backfill_one_event(
    event_dir: Path,
    users: dict,
    users_file_path: str,
    tournaments: dict | None = None,
    unresolved: list | None = None,
) -> bool:
    """1つのイベントディレクトリを再取得し、event_data_version を更新する。

    attr.json が欠落/破損していて event_id を直接読み取れない場合、
    tournaments(tournaments.jsonl の内容)から復元を試みる。復元できない場合は
    [UNRESOLVED] として報告し(unresolved が渡されていれば追記)、処理を継続する
    (例外は送出しない)。

    成功したら True、失敗したら False を返す(呼び出し元は失敗してもスキャンを継続する)。
    """
    try:
        attr = read_json(str(event_dir / "attr.json"))
    except (OSError, ValueError) as exc:
        print(f"[INFO] {event_dir}: attr.json を読み込めません ({exc})。tournaments.jsonl からの復元を試みます。", file=sys.stderr)
        attr = {}

    event_id = attr.get("event_id")
    if event_id is None:
        event_id = _find_event_id_in_tournaments(tournaments, event_dir)
    if event_id is None:
        print(f"[UNRESOLVED] {event_dir}: event_id を特定できません", file=sys.stderr)
        if unresolved is not None:
            unresolved.append(str(event_dir))
        return False

    try:
        event, tournament = fetch_event_details(event_id)
    except FetchError as exc:
        print(f"[{event_id}] fetch failed: {exc}", file=sys.stderr)
        return False

    event_name = event.get("name") or attr.get("event_name") or "Unknown Event"
    tournament_name = tournament.get("name") or attr.get("tournament_name") or "Unknown Tournament"
    timestamp = event.get("startAt") or tournament.get("startAt") or attr.get("timestamp")
    if timestamp is None:
        print(f"[{event_id}] no timestamp available from API. Skipping.", file=sys.stderr)
        return False

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
    )
    print(f"[{event_id}] backfilled to event_data_version={EVENT_DATA_VERSION} ({event_dir})")
    return True


# ---------------------------------------------------------------------------
# 循環スキャン本体
# ---------------------------------------------------------------------------

def run_backfill(
    events_root: Path,
    users_file_path: str,
    cursor_path: Path,
    max_events: int,
    tournament_file_path: str | None = None,
) -> dict:
    """1回の実行分のバックフィルを行い、サマリーを dict で返す。

    {"processed": int, "skipped": int, "wrapped_around": bool, "unresolved": int}
    """
    all_dirs = iter_event_dirs(events_root)
    total = len(all_dirs)
    if total == 0:
        return {"processed": 0, "skipped": 0, "wrapped_around": False, "unresolved": 0}

    dir_strs = [str(d) for d in all_dirs]
    cursor_value = read_cursor(cursor_path)
    start_index = 0
    if cursor_value is not None and cursor_value in dir_strs:
        start_index = (dir_strs.index(cursor_value) + 1) % total

    users = read_users_jsonl(users_file_path)
    tournaments = read_tournaments_jsonl(tournament_file_path) if tournament_file_path else None

    processed = 0
    skipped = 0
    wrapped_around = False
    unresolved_events: list = []
    last_index = None

    for offset in range(total):
        index = (start_index + offset) % total
        if index < start_index:
            wrapped_around = True
        event_dir = all_dirs[index]
        version = read_event_data_version(event_dir)
        if version < EVENT_DATA_VERSION:
            if max_events > 0 and processed >= max_events:
                break
            backfill_one_event(
                event_dir, users, users_file_path,
                tournaments=tournaments, unresolved=unresolved_events,
            )
            processed += 1
            last_index = index
        else:
            skipped += 1
            last_index = index

    if last_index is not None:
        write_cursor(cursor_path, dir_strs[last_index])

    return {
        "processed": processed,
        "skipped": skipped,
        "wrapped_around": wrapped_around,
        "unresolved": len(unresolved_events),
    }


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill outdated event_data_version by re-downloading events from start.gg."
    )
    parser.add_argument("--token", required=True, help="start.gg API token")
    parser.add_argument("--events_root", default="data/startgg/events", help="Events root directory")
    parser.add_argument("--users_file_path", default="data/startgg/users.jsonl", help="Path to users.jsonl")
    parser.add_argument(
        "--tournament_file_path",
        default="data/startgg/tournaments.jsonl",
        help="Path to tournaments.jsonl, used to recover event_id when attr.json is missing.",
    )
    parser.add_argument(
        "--cursor_path",
        default="data/startgg/schema_backfill_cursor.txt",
        help="Path to store and read the backfill scan cursor.",
    )
    parser.add_argument(
        "--max_events",
        type=int,
        default=200,
        help="Maximum number of events to actually re-download in a single run (0 means unlimited).",
    )
    parser.add_argument("--url", default="https://api.start.gg/gql/alpha", help="API URL")
    parser.add_argument("--max_retries", type=int, default=20, help="Maximum number of retries for API requests")
    parser.add_argument("--retry_delay", type=int, default=5, help="Delay between retries in seconds")
    parser.add_argument("--indent_num", type=int, default=2, help="Indentation level for JSON output")
    args = parser.parse_args()

    set_indent_num(args.indent_num)
    set_retry_parameters(args.max_retries, args.retry_delay)
    set_api_parameters(args.url, args.token)

    events_root = Path(args.events_root)
    cursor_path = Path(args.cursor_path)

    print(f"Target event_data_version: {EVENT_DATA_VERSION}")
    print(f"Cursor: {read_cursor(cursor_path) or '(none, starting from the beginning)'}")

    summary = run_backfill(
        events_root, args.users_file_path, cursor_path, args.max_events,
        tournament_file_path=args.tournament_file_path,
    )

    print(
        f"Done. processed={summary['processed']} skipped={summary['skipped']} "
        f"unresolved={summary['unresolved']} "
        f"wrapped_around={str(summary['wrapped_around']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
