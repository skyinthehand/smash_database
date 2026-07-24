#!/usr/bin/env python3
"""matches.json / standings.json の data が空配列になっているイベントを一覧表示する。

2 つのカテゴリに分けて洗い出す:
  - EMPTY_MATCHES  : matches.json の data が空配列（待機リスト枠なども含む）
  - EMPTY_STANDINGS: matches.json は非空なのに standings.json の data が空配列
                      （「試合はあったのに standings が欠けている」実データの欠損）

読み取り専用の確認ツール。ファイルの変更や git add は一切行わない。

使い方:
    python3 scripts/fix/find_empty_events.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def iter_event_dirs(events_root: Path):
    for attr_path in events_root.rglob("attr.json"):
        yield attr_path.parent


def get_event_id(event_dir: Path) -> str:
    attr_path = event_dir / "attr.json"
    try:
        with attr_path.open("r", encoding="utf-8") as f:
            attr = json.load(f)
        return str(attr.get("event_id", "unknown"))
    except (OSError, json.JSONDecodeError):
        return "unknown"


def load_data_list(path: Path):
    """{"data": [...]} の data を返す。読めない場合は None（判定対象外）を返す。"""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return obj.get("data")


def find_empty_events(events_root: Path) -> tuple[list[tuple[Path, str]], list[tuple[Path, str]]]:
    empty_matches = []
    empty_standings = []

    for event_dir in iter_event_dirs(events_root):
        matches = load_data_list(event_dir / "matches.json")
        if matches is None:
            continue

        if matches == []:
            empty_matches.append((event_dir, get_event_id(event_dir)))
            continue

        standings = load_data_list(event_dir / "standings.json")
        if standings is None:
            continue
        if standings == []:
            empty_standings.append((event_dir, get_event_id(event_dir)))

    return empty_matches, empty_standings


def print_section(title: str, results: list[tuple[Path, str]]) -> None:
    if not results:
        print(f"[{title}] 該当するイベントはありませんでした。")
        return
    print(f"[{title}] {len(results)} 件\n")
    for event_dir, event_id in sorted(results, key=lambda r: str(r[0])):
        print(f"event_id={event_id}  {event_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="matches.json / standings.json の data が空配列のイベントを event_id とともに表示する"
    )
    parser.add_argument("--events-root", default="data/startgg/events", help="Events root directory")
    args = parser.parse_args()

    events_root = Path(args.events_root)
    empty_matches, empty_standings = find_empty_events(events_root)

    print_section("EMPTY_MATCHES: matches.json の data が空", empty_matches)
    print()
    print_section("EMPTY_STANDINGS: matches.json は非空なのに standings.json の data が空", empty_standings)


if __name__ == "__main__":
    main()
