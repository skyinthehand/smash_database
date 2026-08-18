#!/usr/bin/env python3
"""standings.json と matches.json が両方とも空(参加者・試合結果が0件)の
イベントディレクトリを検出・削除するツール。

大会の延期時にstart.gg側でイベント自体が作り直された場合、作り直される前の古い
イベントは実データを一切持たないまま残り続ける
(scripts/fetch/backfill_tournament_events.py が新しいイベントを発見する仕組みとは
独立に動作する)。「削除対象のディレクトリが、新しく発見されたイベントと同一実体か
どうか」の判定は行わない。

git add は一切行わない。

使い方:
    # dry-run(削除対象を表示するだけ、デフォルト)
    python3 scripts/fix/prune_empty_events.py

    # 実際に削除
    python3 scripts/fix/prune_empty_events.py --apply
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

from scripts.utils import read_json, read_tournaments_jsonl, write_jsonl  # noqa: E402


def count_data_entries(path) -> int:
    """JSON ファイルの {"data": [...]} の要素数を返す。存在しない/壊れている場合は 0。"""
    try:
        return len(read_json(str(path)).get("data", []))
    except (OSError, ValueError):
        return 0


def is_empty_event(event_dir) -> bool:
    """standings.json と matches.json の両方が空(0件)の場合 True を返す。
    seeds.json / attr.json の中身は判定に使わない。"""
    event_dir = Path(event_dir)
    return (
        count_data_entries(event_dir / "standings.json") == 0
        and count_data_entries(event_dir / "matches.json") == 0
    )


def find_empty_event_dirs(events_root: Path) -> list[Path]:
    """events_root 以下の、standings.json または matches.json を持つディレクトリのうち、
    is_empty_event() が True のものを安定ソート順で返す。"""
    candidates = {p.parent for p in events_root.rglob("standings.json")}
    candidates.update(p.parent for p in events_root.rglob("matches.json"))
    return sorted((d for d in candidates if is_empty_event(d)), key=str)


def prune_empty_events(events_root: Path, tournament_file_path: str, apply: bool) -> dict:
    """空のイベントディレクトリを検出し、apply=True の場合のみ削除する。

    {"found": int, "deleted": int, "deleted_paths": list[str]}
    """
    empty_dirs = find_empty_event_dirs(events_root)
    result = {"found": len(empty_dirs), "deleted": 0, "deleted_paths": []}

    if not empty_dirs:
        return result

    if not apply:
        for event_dir in empty_dirs:
            print(f"[DRY-RUN] would delete empty event directory: {event_dir}")
        return result

    deleted_paths = {str(event_dir) for event_dir in empty_dirs}
    for event_dir in empty_dirs:
        shutil.rmtree(event_dir)
        print(f"Deleted empty event directory: {event_dir}")

    tournaments = read_tournaments_jsonl(tournament_file_path)
    for tournament in tournaments.values():
        tournament["events"] = [
            e for e in tournament.get("events", []) if e.get("path") not in deleted_paths
        ]
    write_jsonl(list(tournaments.values()), tournament_file_path, with_version=True)

    result["deleted"] = len(empty_dirs)
    result["deleted_paths"] = sorted(deleted_paths)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete event directories whose standings.json and matches.json are both empty."
    )
    parser.add_argument("--events_root", default="data/startgg/events", help="Events root directory")
    parser.add_argument(
        "--tournament_file_path",
        default="data/startgg/tournaments.jsonl",
        help="Path to tournaments.jsonl (only read/updated when --apply is set)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete empty directories and update tournaments.jsonl. "
        "Without this flag, only reports what would be deleted.",
    )
    args = parser.parse_args()

    summary = prune_empty_events(Path(args.events_root), args.tournament_file_path, args.apply)

    print(
        f"Done. found={summary['found']} deleted={summary['deleted']} "
        f"apply={str(args.apply).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
