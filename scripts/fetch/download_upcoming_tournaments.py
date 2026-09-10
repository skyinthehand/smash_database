#!/usr/bin/env python3
"""まだ開始されていない(未開催の)start.gg大会の一覧を取得し、
data/startgg/upcoming_tournaments.jsonl に記録するツール。

既存の scripts/fetch/download.py(開催済み大会の履歴収集、冪等incremental)
とは完全に独立している。未開催データは開催日変更・エントリー増減・中止等で
恒常的に変化するため、done.csv的な重複回避は行わず、実行のたびに
upcoming_tournaments.jsonl の内容を全件洗い替えする
(010-upcoming-tournaments、plan.md Complexity Tracking参照)。

data/startgg/tournaments.jsonl・data/startgg/events/配下・done.csv・
done_events.csv はいずれも読み書きしない。git add は一切行わない。

使い方:
    python3 scripts/fetch/download_upcoming_tournaments.py --token <TOKEN> --country_code JP
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.labeling import compute_event_labels  # noqa: E402
from scripts.queries import (  # noqa: E402
    get_event_details_by_id_query,
    get_upcoming_tournaments_by_game_query,
)
from scripts.utils import (  # noqa: E402
    EVENT_DATA_VERSION,
    FetchError,
    fetch_data_with_retries,
    get_page_delay,
    set_api_parameters,
    set_page_delay,
    set_retry_parameters,
    write_jsonl,
)

DEFAULT_GAME_ID = "1386"
DEFAULT_MAX_RETRIES = 20
DEFAULT_RETRY_DELAY = 5
TOURNAMENTS_PER_PAGE = 50


def build_place(tournament: dict) -> dict:
    return {
        "city": tournament.get("city"),
        "lat": tournament.get("lat"),
        "lng": tournament.get("lng"),
        "venue_name": tournament.get("venueName"),
        "timezone": tournament.get("timezone"),
        "postal_code": tournament.get("postalCode"),
        "venue_address": tournament.get("venueAddress"),
        "maps_place_id": tournament.get("mapsPlaceId"),
    }


def fetch_num_entrants_individually(event_id: int) -> int | None:
    """FR-003aのフォールバック: 一覧クエリにネストしたeventsからnumEntrantsが
    取得できなかった場合、この関数でイベント単位の個別クエリを叩いて補完する
    (既存の履歴収集と同じ get_event_details_by_id_query を再利用)。"""
    try:
        response = fetch_data_with_retries(
            get_event_details_by_id_query(),
            {"eventId": event_id},
        )
    except FetchError as exc:
        print(f"Event {event_id}: failed to fetch num_entrants individually: {exc}", file=sys.stderr)
        return None
    event = (response.get("data") or {}).get("event")
    if event is None:
        return None
    return event.get("numEntrants")


def build_event_record(node: dict, tournament_name: str) -> dict:
    event_name = node.get("name")
    num_entrants = node.get("numEntrants")
    if num_entrants is None:
        # 一覧クエリへのネストでnumEntrantsが取得できなかった場合のフォールバック
        # (FR-003a)。ネストが機能していない場合、この分岐が全イベントで発動する
        # ことになるが、それでも必ずnumEntrantsを取得しようとする点で正しい。
        num_entrants = fetch_num_entrants_individually(node.get("id"))

    labels, label_version = compute_event_labels(
        None, tournament_name, event_name, EVENT_DATA_VERSION
    )

    return {
        "event_id": node.get("id"),
        "event_name": event_name,
        "num_entrants": num_entrants,
        "is_online": node.get("isOnline"),
        "state": node.get("state"),
        "type": node.get("type"),
        "labels": labels,
        "label_version": label_version,
    }


def fetch_upcoming_tournaments_by_game(game_id, country_code, after_date, limit=TOURNAMENTS_PER_PAGE, page=1):
    response_data = fetch_data_with_retries(
        get_upcoming_tournaments_by_game_query(country_code, after_date),
        {"gameId": game_id, "perPage": limit, "page": page},
    )
    if (
        "data" not in response_data
        or response_data["data"] is None
        or "tournaments" not in response_data["data"]
        or response_data["data"]["tournaments"] is None
    ):
        raise FetchError(
            "Error: 'data' or 'tournaments' key not found in response for upcoming tournaments "
            f"(game_id={game_id}, country_code={country_code!r}). Response data: {response_data}\n"
            "この絞り込みクエリ(afterDate/eventsネスト)がstart.gg側で無効な可能性があります。"
            "research.md #1/#2のFallback方式の実装を検討してください。"
            " in fetch_upcoming_tournaments_by_game"
        )
    tournaments = response_data["data"]["tournaments"]["nodes"]
    total_pages = response_data["data"]["tournaments"]["pageInfo"]["totalPages"]
    return tournaments, total_pages


def build_tournament_record(tournament: dict, game_id: str, fetched_at: int) -> dict:
    tournament_name = tournament.get("name")
    events = [
        build_event_record(node, tournament_name)
        for node in (tournament.get("events") or [])
    ]
    return {
        "tournament_id": tournament.get("id"),
        "name": tournament_name,
        "country_code": tournament.get("countryCode"),
        "start_at": tournament.get("startAt"),
        "end_at": tournament.get("endAt"),
        "url": tournament.get("url"),
        "place": build_place(tournament),
        "events": events,
        "fetched_at": fetched_at,
        "version": "1.0",
    }


def fetch_all_upcoming_tournaments(game_id, country_code):
    after_date = int(datetime.now().timestamp())
    fetched_at = after_date
    records = []
    page = 1
    while True:
        tournaments, total_pages = fetch_upcoming_tournaments_by_game(
            game_id, country_code, after_date, limit=TOURNAMENTS_PER_PAGE, page=page
        )
        print(f"Progress: {page}/{total_pages}")
        for tournament in tournaments:
            start_at = tournament.get("startAt")
            if start_at is not None and start_at <= after_date:
                # afterDateフィルタがstart.gg側で期待通り効かなかった場合の
                # 防御。開始日時が既に過去(または進行中)の大会は、サーバー側の
                # 絞り込みが効いていても効いていなくても、クライアント側で
                # 確実に除外する(spec.md Edge Cases「開催中の大会は対象外」)。
                print(f"Tournament {tournament.get('id')} startAt is not in the future; skipping.")
                continue
            records.append(build_tournament_record(tournament, game_id, fetched_at))
        if page >= total_pages:
            break
        page += 1
        time.sleep(get_page_delay())
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Fetch upcoming (not-yet-started) start.gg tournaments into "
        "data/startgg/upcoming_tournaments.jsonl (full overwrite every run)."
    )
    parser.add_argument("--token", required=True, help="start.gg API token")
    parser.add_argument("--country_code", default="JP", help="Country code to fetch (default: JP)")
    parser.add_argument("--game_id", default=DEFAULT_GAME_ID, help="Game ID to fetch")
    parser.add_argument("--url", default="https://api.start.gg/gql/alpha", help="API URL")
    parser.add_argument(
        "--tournaments_file",
        default="data/startgg/upcoming_tournaments.jsonl",
        help="Path to write the upcoming-tournaments JSONL file",
    )
    parser.add_argument("--max_retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--retry_delay", type=int, default=DEFAULT_RETRY_DELAY)
    parser.add_argument("--page_delay", type=int, default=2)
    args = parser.parse_args()

    set_retry_parameters(args.max_retries, args.retry_delay)
    set_page_delay(args.page_delay)
    set_api_parameters(args.url, args.token)

    records = fetch_all_upcoming_tournaments(args.game_id, args.country_code)
    write_jsonl(records, args.tournaments_file, with_version=True)

    total_events = sum(len(r["events"]) for r in records)
    print(f"Done. tournaments={len(records)} events={total_events} -> {args.tournaments_file}")


if __name__ == "__main__":
    main()
