#!/usr/bin/env python3
"""matches.json の data は空でないのに、standings.json の data が空配列になっている
イベントを一覧表示する。

matches.json が空のイベント（待機リスト枠など、そもそも試合が存在しないもの）を除外し、
「試合はあったのに standings が欠けている」実データの欠損だけを洗い出す。

読み取り専用の確認ツール。ファイルの変更や git add は一切行わない。

使い方:
    python3 scripts/fix/find_empty_standings.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def iter_event_dirs(events_root: Path):
    for attr_path in events_root.rglob("attr.json"):
        yield attr_path.parent


def find_empty_standings(events_root: Path) -> list[tuple[Path, str]]:
    results = []
    for event_dir in iter_event_dirs(events_root):
        matches_path = event_dir / "matches.json"
        standings_path = event_dir / "standings.json"
        if not matches_path.exists() or not standings_path.exists():
            continue
        try:
            with matches_path.open("r", encoding="utf-8") as f:
                matches = json.load(f)
            with standings_path.open("r", encoding="utf-8") as f:
                standings = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if matches.get("data") == []:
            continue
        if standings.get("data") != []:
            continue

        attr_path = event_dir / "attr.json"
        try:
            with attr_path.open("r", encoding="utf-8") as f:
                attr = json.load(f)
            event_id = attr.get("event_id", "unknown")
        except (OSError, json.JSONDecodeError):
            event_id = "unknown"

        results.append((event_dir, str(event_id)))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="matches.json は非空なのに standings.json の data が空配列のイベントを event_id とともに表示する"
    )
    parser.add_argument("--events-root", default="data/startgg/events", help="Events root directory")
    args = parser.parse_args()

    events_root = Path(args.events_root)
    results = find_empty_standings(events_root)

    if not results:
        print("該当するイベントは見つかりませんでした。")
        return

    print(f"matches.json は非空・standings.json の data が空のイベント: {len(results)} 件\n")
    for event_dir, event_id in sorted(results, key=lambda r: str(r[0])):
        print(f"event_id={event_id}  {event_dir}")


if __name__ == "__main__":
    main()
