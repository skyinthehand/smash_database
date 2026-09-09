#!/usr/bin/env python3
"""data/startgg/excluded_events.json にイベント単位で除外登録されている
event_idについて、data/startgg/tournaments.jsonlのエントリと、対応する
ローカルのイベントディレクトリの両方を削除するツール。

excluded_events.jsonは「今後の自動取得を防ぐ」ためのファイルであり、
既にローカルに存在するデータを遡って削除する機能は無い。そのため、
除外リストに追記しただけでは、過去に取得済みのtournaments.jsonlエントリ・
イベントディレクトリはそのまま残ってしまう。本ツールはその後始末を行う。

除外の妥当性そのものは、ユーザーがexcluded_events.jsonへ追記した時点で
既に確認・確定させているという前提に立つため、start.gg APIへの再確認は
行わない(トークン不要)。

対象はイベント単位除外(値が`reason`を直下に持つオブジェクト形状)のみ。
phase単位除外(値が配列形状、特定phaseGroupのみをsets取得から除外する
別の仕組み)は対象外で、一切変更しない。

git add は一切行わない。

使い方:
    # まずは dry-run(削除対象の一覧を表示するだけ)
    python3 scripts/fix/prune_excluded_events.py

    # 実際にtournaments.jsonl・イベントディレクトリの両方を削除する
    python3 scripts/fix/prune_excluded_events.py --yes
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.fetch.download import load_excluded_event_ids  # noqa: E402
from scripts.fix.check_missing_attr_events import remove_event  # noqa: E402
from scripts.utils import read_set, read_tournaments_jsonl, write_jsonl  # noqa: E402


def find_excluded_events_in_tournaments(tournaments: dict, excluded_event_ids: set) -> list[tuple[int, int, dict]]:
    """tournaments辞書を走査し、除外リストに載っているevent_idを
    (tournament_id, event_id, event) のリストとして列挙する。"""
    found = []
    for tournament_id, entry in tournaments.items():
        for event in entry.get("events", []):
            if event.get("event_id") in excluded_event_ids:
                found.append((tournament_id, event.get("event_id"), event))
    return found


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="excluded_events.jsonにイベント単位で登録されているevent_idを、"
        "tournaments.jsonl・ローカルディレクトリの両方から削除する。"
    )
    parser.add_argument("--tournaments-file", default="data/startgg/tournaments.jsonl")
    parser.add_argument("--excluded-events-file", default="data/startgg/excluded_events.json")
    parser.add_argument("--done-events-file", default="data/startgg/done_events.csv")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="実際にtournaments.jsonl・イベントディレクトリを削除する。"
        "指定しない場合はdry-run(削除対象の一覧表示のみ)。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    excluded_event_ids = set(load_excluded_event_ids(args.excluded_events_file).keys())
    tournaments = read_tournaments_jsonl(args.tournaments_file)
    done_events = read_set(args.done_events_file, as_int=True)

    targets = find_excluded_events_in_tournaments(tournaments, excluded_event_ids)

    print(f"除外リスト(イベント単位): {len(excluded_event_ids)}件")
    print(f"うちtournaments.jsonlに残っているもの: {len(targets)}件\n")

    for tournament_id, event_id, event in targets:
        path = event.get("path")
        dir_exists = bool(path) and os.path.isdir(path)
        done_marker = "YES" if event_id in done_events else "NO"
        print(
            f"  tournament_id={tournament_id} event_id={event_id} path={path} "
            f"dir_exists={dir_exists} done_events.csv={done_marker}"
        )

    if not args.yes:
        print("\nDry-run only. Re-run with --yes to actually remove these from "
              "tournaments.jsonl and delete their directories.")
        return 0

    removed_dirs = 0
    for tournament_id, event_id, event in targets:
        remove_event(tournaments, tournament_id, event_id)
        path = event.get("path")
        if path and os.path.isdir(path):
            shutil.rmtree(path)
            removed_dirs += 1
            print(f"Deleted directory: {path}")

    if targets:
        write_jsonl(list(tournaments.values()), args.tournaments_file, with_version=True)

    print(f"\n{len(targets)}件をtournaments.jsonlから削除し、うち{removed_dirs}件のディレクトリを削除しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
