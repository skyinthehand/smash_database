#!/usr/bin/env python3
"""Repair a detected path collision between two or more event_ids (specs/008-
tournament-path-collision, User Story 4).

`scripts/fix/find_path_collisions.py` が報告した衝突のうち、指定したevent_id群
(同一の同日同名グループに属する2件以上)を対象に、`resolve_path_collision()`と同じ
判定基準(参加者数が最多の1件は元の名前を維持し、残りは重複しない名前へ調整する)で
分離する。全ての対象データは既にディスク上に存在するため、start.gg への再取得は
行わず、既存ディレクトリの移動と `tournaments.jsonl` の更新のみを行う。

`--yes` が無ければ、対象・現在の状態・実行後の見込みを表示するだけで、実際の変更は
一切行わない(FR-009/FR-010)。

使い方:
    # まずは確認のみ
    python3 scripts/fix/fix_path_collision.py --event-id 1642641 1620892

    # 実際に修復する(3件以上もまとめて指定できる)
    python3 scripts/fix/fix_path_collision.py --event-id 1642641 1620892 1700000 --yes
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT_DIR = str(Path(__file__).resolve().parents[2])
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.fetch.download import disambiguated_dir  # noqa: E402
from scripts.utils import get_date_parts, get_event_directory, read_json  # noqa: E402

DEFAULT_TOURNAMENTS = Path("data/startgg/tournaments.jsonl")
DEFAULT_EVENTS_ROOT = Path("data/startgg/events")
JSON_VERSION = "1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair a path collision between two or more event_ids reported by "
            "find_path_collisions.py."
        )
    )
    parser.add_argument(
        "--event-id",
        type=int,
        nargs="+",
        required=True,
        help="event_id(s) sharing the colliding path (2 or more).",
    )
    parser.add_argument(
        "--tournaments-file",
        type=Path,
        default=DEFAULT_TOURNAMENTS,
        help=f"Path to tournaments.jsonl (default: {DEFAULT_TOURNAMENTS})",
    )
    parser.add_argument(
        "--events-root",
        type=Path,
        default=DEFAULT_EVENTS_ROOT,
        help=f"Root directory containing event folders (default: {DEFAULT_EVENTS_ROOT})",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually move directories and update tournaments.jsonl. Without this flag, only a preview is shown.",
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


def write_tournaments(entries: List[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            serialisable = dict(entry)
            serialisable["version"] = JSON_VERSION
            json.dump(serialisable, handle, ensure_ascii=False)
            handle.write("\n")


class Target:
    def __init__(self, event_id: int, tournament_id: int, tournament_entry: dict, event_entry: dict):
        self.event_id = event_id
        self.tournament_id = tournament_id
        self.tournament_entry = tournament_entry
        self.event_entry = event_entry
        self.current_path = Path(event_entry["path"])
        self.attr: Optional[dict] = None
        self.num_entrants = 0
        self.naive_path: Optional[Path] = None
        self.final_path: Optional[Path] = None

    def load_attr(self) -> None:
        attr_path = self.current_path / "attr.json"
        try:
            self.attr = read_json(str(attr_path))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"event_id={self.event_id}: {attr_path} を読み込めません ({exc})") from exc
        self.num_entrants = self.attr.get("num_entrants") or 0

    def compute_naive_path(self, events_root: Path) -> None:
        attr = self.attr
        place = attr.get("place") or {}
        country_code = place.get("country_code") or ""
        timestamp = attr.get("timestamp")
        if timestamp is None:
            raise RuntimeError(f"event_id={self.event_id}: attr.jsonにtimestampがありません。")
        year, month, day = get_date_parts(timestamp)
        self.naive_path = Path(
            get_event_directory(
                str(events_root), country_code, year, month, day,
                attr.get("tournament_name") or "", attr.get("event_name") or "",
            )
        )


def build_event_index(tournaments: List[dict]) -> Dict[int, tuple]:
    """event_id -> (tournament_id, tournament_entry, event_entry)"""
    index: Dict[int, tuple] = {}
    for tournament_entry in tournaments:
        tournament_id = tournament_entry.get("tournament_id")
        for event_entry in tournament_entry.get("events", []):
            event_id = event_entry.get("event_id")
            if event_id is not None:
                index[event_id] = (tournament_id, tournament_entry, event_entry)
    return index


def resolve_targets(event_ids: List[int], tournaments: List[dict], events_root: Path) -> List[Target]:
    index = build_event_index(tournaments)
    targets = []
    for event_id in event_ids:
        if event_id not in index:
            raise RuntimeError(f"event_id={event_id} は {DEFAULT_TOURNAMENTS} に見つかりません。")
        tournament_id, tournament_entry, event_entry = index[event_id]
        target = Target(event_id, tournament_id, tournament_entry, event_entry)
        target.load_attr()
        target.compute_naive_path(events_root)
        targets.append(target)

    naive_paths = {str(t.naive_path) for t in targets}
    if len(naive_paths) > 1:
        details = "\n".join(f"  event_id={t.event_id}: {t.naive_path}" for t in targets)
        raise RuntimeError(
            f"指定されたevent_idは同一の保存先パスに衝突していません:\n{details}"
        )
    return targets


def assign_final_paths(targets: List[Target]) -> Target:
    """参加者数最多(同数ならtournament_idが小さい方)を勝者とし、naive_pathを割り当てる。
    残りはdisambiguated_dir()で調整した名前を final_path に割り当てる
    (resolve_path_collision()と同じ判定基準。research.md Decision 3)。"""
    winner = min(
        targets,
        key=lambda t: (-t.num_entrants, t.tournament_id),
    )
    for target in targets:
        if target is winner:
            target.final_path = target.naive_path
        else:
            target.final_path = Path(disambiguated_dir(str(target.naive_path), target.tournament_id))
    return winner


def move_event_dir(src: Path, dst: Path) -> None:
    if src == dst:
        return
    if not src.is_dir():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_dir():
        shutil.rmtree(dst)
    shutil.move(str(src), str(dst))


def main() -> int:
    args = parse_args()

    if len(set(args.event_id)) < 2:
        print("--event-id には異なるevent_idを2件以上指定してください。", file=sys.stderr)
        return 1

    if not args.tournaments_file.is_file():
        print(f"{args.tournaments_file} が見つかりません。", file=sys.stderr)
        return 1

    tournaments = load_tournaments(args.tournaments_file)
    try:
        targets = resolve_targets(args.event_id, tournaments, args.events_root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    winner = assign_final_paths(targets)

    print("対象:")
    for target in targets:
        role = "維持(元の名前)" if target is winner else "調整(重複しない名前へ)"
        print(
            f"  event_id={target.event_id} tournament_id={target.tournament_id} "
            f"num_entrants={target.num_entrants}\n"
            f"    現在: {target.current_path}\n"
            f"    実行後: {target.final_path} [{role}]"
        )

    if not args.yes:
        print("\nDry-run only. Re-run with --yes to actually move directories and update tournaments.jsonl.")
        return 0

    for target in targets:
        move_event_dir(target.current_path, target.final_path)
        target.event_entry["path"] = str(target.final_path)

    write_tournaments(tournaments, args.tournaments_file)
    print(f"\n{args.tournaments_file} を更新しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
