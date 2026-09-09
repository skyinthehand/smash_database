#!/usr/bin/env python3
"""tournaments.jsonl に記載されているイベントのうち、path配下にattr.jsonが
存在しないものを洗い出し、start.ggでまだ公開されているかどうかを確認する
読み取り専用の診断ツール(--yes指定時のみtournaments.jsonlへの書き込みを行う)。

attr.jsonが無いイベントは、start.gg側の event(id: eventId) を問い合わせて
3種類に分類する:
- gone: dataにerrorsが付かず event が null → start.gg側で確認済みに
  削除/非公開。--yes指定時、tournaments.jsonlから該当イベントを削除する
  (該当tournamentの他のイベントは保持し、events配列が空になった場合のみ
  tournamentのエントリごと削除する)。
- found: event にデータがある → まだ公開されている。削除は一切行わず、
  手動での再取得を促すために表示するのみ。
- inconclusive: data/eventキーが無い、errorsが付いている、または
  fetch_data_with_retriesが最終的に例外を送出した場合。判断材料が
  無いため削除しない(fail-closed)。

git add は一切行わない。

使い方:
    # まずは dry-run(削除は行わず、分類結果を表示するだけ)
    python3 scripts/fix/check_missing_attr_events.py --token <TOKEN>

    # gone判定のイベントを実際にtournaments.jsonlから削除する
    python3 scripts/fix/check_missing_attr_events.py --token <TOKEN> --yes
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.queries import get_event_details_by_id_query  # noqa: E402
from scripts.utils import (  # noqa: E402
    FetchError,
    fetch_data_with_retries,
    read_set,
    read_tournaments_jsonl,
    set_api_parameters,
    set_retry_parameters,
    write_jsonl,
)


def find_events_missing_attr(tournaments: dict) -> list[tuple[int, int, dict]]:
    """tournaments辞書を走査し、(tournament_id, event_id, event)のうち
    event["path"]配下にattr.jsonが存在しないものを列挙する。"""
    missing = []
    for tournament_id, entry in tournaments.items():
        for event in entry.get("events", []):
            path = event.get("path")
            if not path:
                continue
            if not os.path.exists(os.path.join(path, "attr.json")):
                missing.append((tournament_id, event.get("event_id"), event))
    return missing


def fetch_event_publication_status(event_id: int) -> tuple[str, dict | str | None]:
    """start.ggにevent_idを問い合わせ、("gone"|"found"|"inconclusive", detail)を返す。
    detailはfoundの場合は取得できたeventのdict、inconclusiveの場合は理由の文字列、
    goneの場合はNone。"""
    try:
        response = fetch_data_with_retries(
            get_event_details_by_id_query(),
            {"eventId": event_id},
        )
    except FetchError as exc:
        return "inconclusive", f"fetch failed: {exc}"

    if "data" not in response or response["data"] is None or "event" not in response["data"]:
        return "inconclusive", f"malformed response: {response}"

    if response.get("errors"):
        return "inconclusive", f"GraphQL errors present: {response['errors']}"

    event = response["data"]["event"]
    if event is None:
        return "gone", None
    return "found", event


def remove_event(tournaments: dict, tournament_id: int, event_id: int) -> None:
    """tournaments[tournament_id]["events"]から該当event_idを取り除く。
    結果としてeventsが空になった場合はtournament_idのエントリごと削除する。"""
    entry = tournaments[tournament_id]
    entry["events"] = [e for e in entry.get("events", []) if e.get("event_id") != event_id]
    if not entry["events"]:
        del tournaments[tournament_id]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="tournaments.jsonl内のattr.json欠落イベントを検出し、"
        "start.gg側で非公開と確認できたものだけtournaments.jsonlから削除する。"
    )
    parser.add_argument("--token", required=True, help="start.gg API token")
    parser.add_argument("--tournaments-file", default="data/startgg/tournaments.jsonl")
    parser.add_argument("--done-events-file", default="data/startgg/done_events.csv")
    parser.add_argument("--api-url", default="https://api.start.gg/gql/alpha")
    parser.add_argument("--max-retries", type=int, default=20)
    parser.add_argument("--retry-delay", type=int, default=5)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="gone判定のイベントを実際にtournaments.jsonlから削除する。"
        "指定しない場合はdry-run(分類結果の表示のみ)。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    set_retry_parameters(args.max_retries, args.retry_delay)
    set_api_parameters(args.api_url, args.token)

    tournaments = read_tournaments_jsonl(args.tournaments_file)
    done_events = read_set(args.done_events_file, as_int=True)

    missing = find_events_missing_attr(tournaments)
    print(f"attr.jsonが存在しないイベント: {len(missing)}件\n")

    gone = []
    found = []
    inconclusive = []
    for tournament_id, event_id, event in missing:
        status, detail = fetch_event_publication_status(event_id)
        if status == "gone":
            gone.append((tournament_id, event_id, event))
        elif status == "found":
            found.append((tournament_id, event_id, event, detail))
        else:
            inconclusive.append((tournament_id, event_id, event, detail))

    print(f"=== start.gg側で削除/非公開と確認できた(gone): {len(gone)}件 ===")
    for tournament_id, event_id, event in gone:
        done_marker = "YES" if event_id in done_events else "NO"
        print(
            f"  tournament_id={tournament_id} event_id={event_id} "
            f"path={event.get('path')} done_events.csv={done_marker}"
        )

    print(f"\n=== まだstart.gg上に存在する(found、要手動確認): {len(found)}件 ===")
    for tournament_id, event_id, event, api_event in found:
        print(
            f"  tournament_id={tournament_id} event_id={event_id} "
            f"path={event.get('path')} "
            f"start.gg上の名前={api_event.get('name')!r} "
            f"tournament={(api_event.get('tournament') or {}).get('name')!r} "
            f"state={api_event.get('state')!r} "
            f"slug={api_event.get('slug')!r} "
            f"tournament_slug={(api_event.get('tournament') or {}).get('slug')!r}"
        )

    print(f"\n=== 判定不能(inconclusive、削除しない): {len(inconclusive)}件 ===")
    for tournament_id, event_id, event, reason in inconclusive:
        print(f"  tournament_id={tournament_id} event_id={event_id} path={event.get('path')} 理由={reason}")

    if not args.yes:
        print("\nDry-run only. Re-run with --yes to actually remove the 'gone' events from tournaments.jsonl.")
        return 0

    for tournament_id, event_id, _event in gone:
        remove_event(tournaments, tournament_id, event_id)
    write_jsonl(list(tournaments.values()), args.tournaments_file, with_version=True)
    print(f"\n{len(gone)}件をtournaments.jsonlから削除しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
