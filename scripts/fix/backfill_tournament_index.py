#!/usr/bin/env python3
"""tournaments.jsonl の抜け(=既にローカルにデータを取得済みなのに未登録の
イベント)を検出・補完するツール。

start.gg のトーナメント一覧を新しい順に全期間分たどり(通常のクロール
download_all_tournaments と同じページング・ディレクトリ計算ロジックを使う)、
各イベントに対応するディレクトリが既にローカルに存在するにもかかわらず
tournaments.jsonl に未登録の場合のみ追加する。まだダウンロードしていない
イベントは対象外(そちらは通常のクロールに任せる)。

イベント自体のデータ(attr/matches/standings/seeds)は一切取得・更新しない。
更新するのは tournaments.jsonl のみ。

使い方:
    python3 scripts/fix/backfill_tournament_index.py --token <TOKEN>
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.fetch.download import (  # noqa: E402
    TOURNAMENTS_PER_PAGE,
    fetch_event_ids_from_tournament,
    fetch_latest_tournaments_by_game,
    record_event_path,
)
from scripts.utils import (  # noqa: E402
    FetchError,
    NoEventsForGameError,
    extend_jsonl,
    get_date_parts,
    get_event_directory,
    read_tournaments_jsonl,
    set_api_parameters,
    set_indent_num,
    set_retry_parameters,
    write_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan the full start.gg tournament history for a game and register any event "
            "whose data directory already exists locally but is missing from tournaments.jsonl."
        )
    )
    parser.add_argument("--token", required=True, help="start.gg API token")
    parser.add_argument("--url", default="https://api.start.gg/gql/alpha", help="API URL")
    parser.add_argument("--game_id", default="1386", help="Game ID for tournament retrieval.")
    parser.add_argument(
        "--country_code",
        default="",
        help="Country code filter (e.g. JP). Empty scans all countries (default, matches the normal crawl).",
    )
    parser.add_argument("--startgg_dir", default="data/startgg/events", help="Directory containing event data")
    parser.add_argument(
        "--tournament_file_path", default="data/startgg/tournaments.jsonl", help="Path to tournaments.jsonl"
    )
    parser.add_argument("--max_retries", type=int, default=100, help="Maximum number of retries for API requests")
    parser.add_argument("--retry_delay", type=int, default=5, help="Delay between retries in seconds")
    parser.add_argument("--indent_num", type=int, default=2, help="Indentation level for JSON output")
    parser.add_argument("--start_page", type=int, default=1, help="Tournament list page to start from (for resuming).")
    parser.add_argument(
        "--max_pages",
        type=int,
        default=None,
        help=(
            "Stop after scanning this many tournament-list pages (useful for a quick smoke "
            "test, including with --dry-run). Default: unlimited (scans full history)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be added without writing tournaments.jsonl.",
    )
    return parser.parse_args()


def scan_and_fill(
    game_id: str,
    country_code: str,
    startgg_dir: str,
    tournament_file_path: str,
    start_page: int = 1,
    max_pages: int | None = None,
    dry_run: bool = False,
) -> dict:
    """全期間のトーナメント履歴を走査し、既にローカルに存在するが tournaments.jsonl に
    未登録のイベントを追加する。max_pages を指定すると、start_page からその件数分の
    ページを走査した時点で打ち切る(--dry-run での動作確認用)。

    戻り値: {"tournaments_scanned": int, "events_added": int, "tournaments_added": int,
             "pages": int}
    """
    tournaments = read_tournaments_jsonl(tournament_file_path)
    existing_tournament_ids = set(tournaments.keys())
    rewrite_tournaments = False

    now_timestamp = int(datetime.now().timestamp())
    tournaments_scanned = 0
    events_added = 0
    tournaments_added = 0
    page = start_page

    while True:
        try:
            tournaments_info, total_pages = fetch_latest_tournaments_by_game(
                game_id, country_code=country_code, limit=TOURNAMENTS_PER_PAGE, page=page
            )
        except FetchError as e:
            print(e, file=sys.stderr)
            continue

        print(f"Progress: page {page}/{total_pages} (events_added so far: {events_added})")
        if not tournaments_info:
            break

        for tournament in tournaments_info:
            tournament_id = tournament["id"]
            tournament_name = tournament["name"]
            timestamp = tournament["startAt"]
            end_timestamp = tournament["endAt"]
            country = tournament["countryCode"]

            if end_timestamp is None or end_timestamp > now_timestamp:
                # 未終了のトーナメントはイベント構成が確定しないためスキップ(通常のクロールと同じ扱い)。
                continue

            tournaments_scanned += 1

            try:
                events_info = fetch_event_ids_from_tournament(tournament_id, game_id)
            except NoEventsForGameError:
                continue
            except FetchError as e:
                print(f"Tournament {tournament_id}: fetch failed, skipping. Error: {e}", file=sys.stderr)
                continue

            if not events_info:
                continue

            year, month, day = get_date_parts(timestamp)
            is_new_tournament = tournament_id not in tournaments

            for event_id, event_name, is_online, state, event_type in events_info:
                event_dir = get_event_directory(
                    startgg_dir, country, year, month, day, tournament_name, event_name
                )
                if not os.path.isdir(event_dir):
                    # まだダウンロードしていないイベントは対象外(通常のクロールに任せる)。
                    continue

                if tournament_id in tournaments:
                    tournaments[tournament_id]["name"] = tournament_name
                    tournaments[tournament_id].setdefault("events", [])
                else:
                    tournaments[tournament_id] = {
                        "tournament_id": tournament_id,
                        "name": tournament_name,
                        "events": [],
                    }

                changed = record_event_path(tournaments, tournament_id, event_id, event_name, event_dir)
                if changed:
                    events_added += 1
                    print(f"[ADD] tournament_id={tournament_id} event_id={event_id} path={event_dir}")
                    if tournament_id in existing_tournament_ids:
                        rewrite_tournaments = True

            if is_new_tournament and tournament_id in tournaments and len(tournaments[tournament_id]["events"]) > 0:
                tournaments_added += 1
                if not dry_run:
                    extend_jsonl([tournaments[tournament_id]], tournament_file_path, with_version=True)
                existing_tournament_ids.add(tournament_id)

        if not dry_run and rewrite_tournaments:
            write_jsonl(list(tournaments.values()), tournament_file_path, with_version=True)
            rewrite_tournaments = False

        if max_pages is not None and (page - start_page + 1) >= max_pages:
            print(f"Reached --max_pages={max_pages}; stopping.")
            break

        if page >= total_pages:
            break
        page += 1

    if not dry_run and rewrite_tournaments:
        write_jsonl(list(tournaments.values()), tournament_file_path, with_version=True)

    return {
        "tournaments_scanned": tournaments_scanned,
        "events_added": events_added,
        "tournaments_added": tournaments_added,
        "pages": page,
    }


def main() -> int:
    args = parse_args()

    set_indent_num(args.indent_num)
    set_retry_parameters(args.max_retries, args.retry_delay)
    set_api_parameters(args.url, args.token)

    summary = scan_and_fill(
        args.game_id,
        args.country_code,
        args.startgg_dir,
        args.tournament_file_path,
        start_page=args.start_page,
        max_pages=args.max_pages,
        dry_run=args.dry_run,
    )

    print(
        f"Done. tournaments_scanned={summary['tournaments_scanned']} "
        f"events_added={summary['events_added']} tournaments_added={summary['tournaments_added']} "
        f"pages={summary['pages']}"
    )
    if args.dry_run:
        print("Dry-run mode: tournaments.jsonl was not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
