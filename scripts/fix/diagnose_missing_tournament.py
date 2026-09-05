#!/usr/bin/env python3
"""特定のstart.ggトーナメント/イベントが、まだ `data/startgg/events` に登録されて
いない理由を診断する読み取り専用ツール。

日次取得(`scripts/fetch/download.py`、`.github/workflows/update_tournament.yml`)が
そのトーナメントを対象外にしている可能性のある条件
(終了未確定・countryCodeの不一致・対象ゲームへの未紐付け等)を、start.gg APIへの
直接照会とローカルデータ(`tournaments.jsonl`/`done.csv`/`done_events.csv`/
`excluded_events.json`)との突き合わせで確認する。`attr.json`等への書き込みは
一切行わない。

使い方:
    # URLから調べる
    python3 scripts/fix/diagnose_missing_tournament.py \\
        --token <TOKEN> \\
        --url "https://www.start.gg/tournament/<slug>/event/<slug>"

    # スラッグを直接指定する場合
    python3 scripts/fix/diagnose_missing_tournament.py \\
        --token <TOKEN> --tournament-slug <slug> --event-slug <slug>
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = str(Path(__file__).resolve().parents[2])
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.fetch.download import fetch_event_ids_from_tournament  # noqa: E402
from scripts.fetch.download_specific_event import fetch_event_details_by_slug  # noqa: E402
from scripts.utils import (  # noqa: E402
    FetchError,
    NoEventsForGameError,
    read_json,
    read_set,
    read_tournaments_jsonl,
    set_api_parameters,
    set_retry_parameters,
)

DEFAULT_GAME_ID = "1386"
URL_PATTERN = re.compile(r"/tournament/([^/]+)/event/([^/]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose why a specific start.gg tournament/event has not been ingested yet."
    )
    parser.add_argument("--token", required=True, help="start.gg API token")
    parser.add_argument("--url", default=None, help="Full start.gg tournament/event URL")
    parser.add_argument("--tournament-slug", default=None, help="Tournament slug (alternative to --url)")
    parser.add_argument("--event-slug", default=None, help="Event slug (alternative to --url)")
    parser.add_argument(
        "--game-id", default=DEFAULT_GAME_ID,
        help=f"Game ID expected by the daily fetch (default: {DEFAULT_GAME_ID})",
    )
    parser.add_argument(
        "--country-code", default="JP",
        help="Country code filter used by the daily fetch (default: JP; pass '' to skip this check)",
    )
    parser.add_argument("--tournaments-file", default="data/startgg/tournaments.jsonl")
    parser.add_argument("--done-file", default="data/startgg/done.csv")
    parser.add_argument("--done-events-file", default="data/startgg/done_events.csv")
    parser.add_argument("--excluded-events-file", default="data/startgg/excluded_events.json")
    parser.add_argument("--api-url", default="https://api.start.gg/gql/alpha")
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--retry-delay", type=int, default=5)
    args = parser.parse_args()

    if args.url:
        m = URL_PATTERN.search(args.url)
        if not m:
            parser.error(
                "--urlから tournament/event のスラッグを抽出できませんでした "
                "(期待する形式: https://www.start.gg/tournament/<slug>/event/<slug>)。"
                "--tournament-slug/--event-slugを直接指定してください。"
            )
        args.tournament_slug, args.event_slug = m.group(1), m.group(2)

    if not args.tournament_slug or not args.event_slug:
        parser.error("--url か、--tournament-slug と --event-slug の両方を指定してください。")

    return args


def load_local_state(args: argparse.Namespace):
    tournaments = read_tournaments_jsonl(args.tournaments_file)
    done_tournaments = read_set(args.done_file, as_int=True)
    done_events = read_set(args.done_events_file, as_int=True)
    try:
        excluded = read_json(args.excluded_events_file)
    except (FileNotFoundError, ValueError):
        excluded = {}
    return tournaments, done_tournaments, done_events, excluded


def _fmt_ts(ts):
    return f"{ts} ({datetime.fromtimestamp(ts)})" if ts else str(ts)


def main() -> int:
    args = parse_args()
    set_retry_parameters(args.max_retries, args.retry_delay)
    set_api_parameters(args.api_url, args.token)

    print(f"tournament_slug={args.tournament_slug!r} event_slug={args.event_slug!r}")
    event = fetch_event_details_by_slug(args.tournament_slug, args.event_slug)
    if event is None:
        print(
            "\nstart.ggからイベント詳細を取得できませんでした"
            "(スラッグの誤り・非公開・削除済みの可能性があります。上記のエラー出力も確認してください)。",
            file=sys.stderr,
        )
        return 1

    tournament = event["tournament"]
    tournament_id = tournament["id"]
    event_id = event["id"]

    print("\n=== start.ggから取得した情報 ===")
    print(f"tournament_id={tournament_id} name={tournament['name']!r}")
    print(f"  countryCode={tournament['countryCode']!r}  venueName={tournament.get('venueName')!r}")
    print(f"  endAt={_fmt_ts(tournament['endAt'])}")
    print(f"event_id={event_id} name={event['name']!r} state={event.get('state')!r} numEntrants={event.get('numEntrants')}")
    print(f"  startAt={_fmt_ts(event.get('startAt'))}  isOnline={event.get('isOnline')}  type={event.get('type')}")

    tournaments, done_tournaments, done_events, excluded = load_local_state(args)

    print("\n=== ローカルデータとの照合 ===")
    local_entry = tournaments.get(tournament_id)
    local_event_ids = {e.get("event_id") for e in local_entry.get("events", [])} if local_entry else set()
    print(f"tournaments.jsonlに存在するか: {'YES' if local_entry else 'NO'}"
          + (f" (登録済みevent_id: {sorted(local_event_ids)})" if local_entry else ""))
    print(f"done.csvに存在するか(tournament単位): {'YES' if tournament_id in done_tournaments else 'NO'}")
    print(f"done_events.csvに存在するか(event単位): {'YES' if event_id in done_events else 'NO'}")
    print(f"excluded_events.jsonに登録されているか: {'YES' if str(event_id) in excluded else 'NO'}")

    now_ts = int(datetime.now().timestamp())
    reasons = []

    if event_id in local_event_ids:
        reasons.append(
            "実は既にtournaments.jsonlに登録済みです。data/startgg/events配下の該当パスに"
            "attr.json等が実際に存在するか、生成が未完了(取得が中断)になっていないかを確認してください。"
        )

    if tournament["endAt"] is None or tournament["endAt"] > now_ts:
        reasons.append(
            "トーナメントがまだ終了していません(endAtが未設定または未来の日時)。"
            "日次取得(update_tournament.yml)は終了済みのトーナメントのみを対象にするため、"
            "終了後の次回実行以降で自動的に取得されるはずです。"
        )

    if args.country_code and (tournament["countryCode"] or "") != args.country_code:
        reasons.append(
            f"トーナメントのcountryCodeが{tournament['countryCode']!r}であり、"
            f"日次取得のフィルタ({args.country_code!r})と一致しません。"
            "start.gg上で会場の国が正しく設定されていない可能性があります。"
        )

    try:
        events_for_game = fetch_event_ids_from_tournament(tournament_id, args.game_id)
        game_event_ids = {e[0] for e in events_for_game}
        if event_id not in game_event_ids:
            reasons.append(
                f"このイベント(event_id={event_id})はgame_id={args.game_id}に紐づく"
                f"イベント一覧({sorted(game_event_ids)})に含まれていません。"
                "start.gg上で対象ゲームの設定を確認してください。"
            )
    except NoEventsForGameError:
        reasons.append(
            f"このトーナメントにはgame_id={args.game_id}(日次取得の対象ゲーム)に紐づく"
            "イベントが1件もありません。start.gg上でゲームの設定を確認してください。"
        )
    except FetchError as exc:
        reasons.append(f"game_id={args.game_id}のイベント一覧取得中にエラーが発生しました: {exc}")

    print("\n=== 診断結果 ===")
    if reasons:
        for r in reasons:
            print(f"- {r}")
    else:
        print(
            "上記の既知の除外条件(未終了・countryCode不一致・対象ゲーム未紐付け・登録済み)"
            "には該当しませんでした。日次取得のスキャン範囲(finish_date)から漏れている、"
            "または一時的なAPIエラーで毎回スキップされ続けている可能性があります。\n"
            "手動で取り込む場合は、次のコマンドで直接ダウンロードできます:\n"
            f"  python3 scripts/fetch/download_specific_event.py --token <TOKEN>\n"
            f"  (事前に target_events に (\"{args.tournament_slug}\", \"{args.event_slug}\") を追加してください)"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
