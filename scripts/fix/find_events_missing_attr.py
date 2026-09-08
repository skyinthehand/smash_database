#!/usr/bin/env python3
"""matches.json/standings.json/seeds.json は存在するのに attr.json だけが
欠けているイベントディレクトリを、data/startgg/events 配下から走査して検出する
読み取り専用ツール。書き込みは一切行わない。ネットワークアクセスも不要
(ローカルファイルの走査のみ)。

背景: 通常の scripts/fetch/download.py の実行では、matches.json が完全に
解決された(プレースホルダーが0件になった)直後に write_event_attributes() で
attr.json を書く。しかし --matches_only モードのリフレッシュは attr.json を
書かないため、fallback(逐次取得)モードで残っていたプレースホルダーが
--matches_only の実行で解決してしまうと、matches.json は完全なのに attr.json が
永久に欠けたままになり得る。本ツールはこの想定外パターンと、単に取得の途中
(プレースホルダーが残っている)想定内パターンを区別して報告する。

使い方:
    python3 scripts/fix/find_events_missing_attr.py
    python3 scripts/fix/find_events_missing_attr.py --events-root data/startgg/events
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = str(Path(__file__).resolve().parents[2])
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.fetch.download import build_path_index  # noqa: E402
from scripts.utils import read_json, read_set, read_tournaments_jsonl  # noqa: E402

DATA_FILES = ("matches.json", "standings.json", "seeds.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="attr.jsonだけが欠けているイベントディレクトリを検出する(読み取り専用)。"
    )
    parser.add_argument("--events-root", default="data/startgg/events")
    parser.add_argument("--tournaments-file", default="data/startgg/tournaments.jsonl")
    parser.add_argument("--done-file", default="data/startgg/done.csv")
    parser.add_argument("--done-events-file", default="data/startgg/done_events.csv")
    return parser.parse_args()


def count_placeholders(matches_path):
    """matches.json の (プレースホルダー件数, 総件数) を返す。読めない場合は None。"""
    try:
        payload = read_json(matches_path)
    except (FileNotFoundError, ValueError):
        return None
    records = payload.get("data") or []
    placeholder_count = sum(1 for r in records if "winner_id" not in r)
    return placeholder_count, len(records)


def find_missing_attr_dirs(events_root):
    """attr.jsonが無く、かつDATA_FILESのいずれかを含むディレクトリを列挙する。"""
    for dirpath, _dirnames, filenames in os.walk(events_root):
        filenames_set = set(filenames)
        if "attr.json" in filenames_set:
            continue
        if not filenames_set & set(DATA_FILES):
            continue
        yield dirpath, filenames_set


def main() -> int:
    args = parse_args()

    tournaments = read_tournaments_jsonl(args.tournaments_file)
    path_index = build_path_index(tournaments)
    done_tournaments = read_set(args.done_file, as_int=True)
    done_events = read_set(args.done_events_file, as_int=True)

    still_incomplete = []
    resolved = []
    unknown = []

    for dirpath, filenames_set in find_missing_attr_dirs(args.events_root):
        ids = path_index.get(dirpath)
        if "matches.json" not in filenames_set:
            unknown.append((dirpath, ids, "matches.jsonも無い", filenames_set))
            continue
        result = count_placeholders(os.path.join(dirpath, "matches.json"))
        if result is None:
            unknown.append((dirpath, ids, "matches.jsonが壊れている", filenames_set))
            continue
        placeholder_count, total = result
        if placeholder_count > 0:
            still_incomplete.append((dirpath, ids, placeholder_count, total))
        else:
            resolved.append((dirpath, ids, total))

    def fmt_ids(ids):
        return f"tournament_id={ids[0]} event_id={ids[1]}" if ids else "(tournaments.jsonl未登録)"

    print(
        f"=== matches.jsonに未解決のプレースホルダーがある(想定内、次回runで解決見込み): "
        f"{len(still_incomplete)}件 ==="
    )
    for dirpath, ids, placeholder_count, total in still_incomplete:
        print(f"  {dirpath}  [{fmt_ids(ids)}]  placeholders={placeholder_count}/{total}")

    print(
        f"\n=== matches.jsonは完全に解決済みなのにattr.jsonが無い(想定外、要調査): "
        f"{len(resolved)}件 ==="
    )
    for dirpath, ids, total in resolved:
        done_marker = ""
        if ids:
            tournament_id, event_id = ids
            done_marker = (
                f" done.csv={'YES' if tournament_id in done_tournaments else 'NO'}"
                f" done_events.csv={'YES' if event_id in done_events else 'NO'}"
            )
        print(f"  {dirpath}  [{fmt_ids(ids)}]  records={total}{done_marker}")

    if unknown:
        print(f"\n=== 判定不能(matches.json自体が無い/壊れている): {len(unknown)}件 ===")
        for dirpath, ids, reason, filenames_set in unknown:
            print(f"  {dirpath}  {reason}  files={sorted(filenames_set)}")

    print(
        f"\n合計: still_incomplete={len(still_incomplete)} "
        f"resolved_but_missing_attr={len(resolved)} unknown={len(unknown)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
