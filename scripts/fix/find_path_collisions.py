#!/usr/bin/env python3
"""Report path collisions in tournaments.jsonl (same-day same-name tournaments).

`tournaments.jsonl` を読み込み、地域/開催日/大会名/イベント名から計算される保存先
ディレクトリパス(`path`)が、異なる`tournament_id`のイベント間で衝突している組み合わせ
を一覧表示する。read-only、API呼び出し無し(specs/008-tournament-path-collision/
research.md Decision 5)。

使い方:
    python3 scripts/fix/find_path_collisions.py
    python3 scripts/fix/find_path_collisions.py --tournaments-file data/startgg/tournaments.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

DEFAULT_TOURNAMENTS = Path("data/startgg/tournaments.jsonl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report cases where two or more distinct tournament_ids share the same "
            "computed event directory path in tournaments.jsonl."
        )
    )
    parser.add_argument(
        "--tournaments-file",
        type=Path,
        default=DEFAULT_TOURNAMENTS,
        help=f"Path to tournaments.jsonl (default: {DEFAULT_TOURNAMENTS})",
    )
    return parser.parse_args()


def load_tournaments(path: Path) -> List[dict]:
    entries: List[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def group_events_by_path(tournaments: List[dict]) -> Dict[str, List[dict]]:
    """`path` -> [{"tournament_id", "tournament_name", "event_id", "event_name"}, ...]"""
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for entry in tournaments:
        tournament_id = entry.get("tournament_id")
        tournament_name = entry.get("name")
        events = entry.get("events", [])
        if not isinstance(events, list):
            continue
        for event in events:
            path = event.get("path")
            if not isinstance(path, str):
                continue
            grouped[path].append(
                {
                    "tournament_id": tournament_id,
                    "tournament_name": tournament_name,
                    "event_id": event.get("event_id"),
                    "event_name": event.get("event_name"),
                }
            )
    return grouped


def find_collisions(grouped: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """同一pathに異なるtournament_idが2件以上紐づいている組み合わせのみを返す。"""
    collisions = {}
    for path, members in grouped.items():
        distinct_tournament_ids = {member["tournament_id"] for member in members}
        if len(distinct_tournament_ids) >= 2:
            collisions[path] = members
    return collisions


def main() -> int:
    args = parse_args()

    if not args.tournaments_file.is_file():
        print(f"{args.tournaments_file} が見つかりません。", file=sys.stderr)
        return 1

    tournaments = load_tournaments(args.tournaments_file)
    grouped = group_events_by_path(tournaments)
    collisions = find_collisions(grouped)

    if not collisions:
        print("保存先パスの衝突は見つかりませんでした。")
        return 0

    print(f"{len(collisions)}件の保存先パス衝突が見つかりました:")
    for path, members in collisions.items():
        print(f"\n- path: {path}")
        for member in members:
            print(
                f"    tournament_id={member['tournament_id']} "
                f"({member['tournament_name']}) "
                f"event_id={member['event_id']} ({member['event_name']})"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
