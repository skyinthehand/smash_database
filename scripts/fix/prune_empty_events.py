#!/usr/bin/env python3
"""standings.json と matches.json が両方とも空(参加者・試合結果が0件)の
イベントディレクトリを検出し、start.gg側で今も本当に空であることを確認した上で
削除するツール。

ローカルのファイルが空であることは「本当に空」を意味しない ── 大会が
`endAt` を過ぎた時点で取得されたが、その後start.gg側でイベントが延期・作り直され
実データが確定した場合、ローカルには古い(空の)スナップショットが残ったままになる
(第7回チバスマ交流会・187-7-23verで実際に発生した事象)。そのため、削除の前に
必ず次の2段階の確認を行う:

  1. 同じ event_id を直接再取得する(event(id: $eventId) 経由)。実データが
     見つかった場合はそれを保存し、削除しない(自動的に最新化される)。
  2. まだ空の場合、同じトーナメント配下に(記録されていない)別のスマブラSPの
     イベントが無いかを確認する。確認できた場合(見つかった/APIで確認不能)は
     削除しない。トーナメント配下に対象ゲームのイベントが他に無いことを確認できた
     場合のみ、削除する。

どちらの確認も曖昧な場合(APIエラー等で判断がつかない場合)は削除しない
(安全側に倒す)。

git add は一切行わない。

使い方:
    # dry-run(削除候補の件数を表示するだけ、API呼び出し無し、デフォルト)
    python3 scripts/fix/prune_empty_events.py --token <TOKEN>

    # 実際に確認・削除
    python3 scripts/fix/prune_empty_events.py --token <TOKEN> --apply
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

from scripts.fetch.backfill_schema_version import backfill_one_event  # noqa: E402
from scripts.fetch.download import fetch_event_ids_from_tournament  # noqa: E402
from scripts.utils import (  # noqa: E402
    FetchError,
    read_json,
    read_tournaments_jsonl,
    read_users_jsonl,
    set_api_parameters,
    set_indent_num,
    set_retry_parameters,
    write_jsonl,
)


# ---------------------------------------------------------------------------
# ローカル判定(一次選別)
# ---------------------------------------------------------------------------

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
    is_empty_event() が True のものを安定ソート順で返す(あくまで一次選別。
    実際の削除可否は start.gg への再確認後に決める)。"""
    candidates = {p.parent for p in events_root.rglob("standings.json")}
    candidates.update(p.parent for p in events_root.rglob("matches.json"))
    return sorted((d for d in candidates if is_empty_event(d)), key=str)


# ---------------------------------------------------------------------------
# start.gg への再確認・削除可否判定
# ---------------------------------------------------------------------------

def resolve_event_id(event_dir: Path, tournaments: dict) -> int | None:
    """attr.json から、無ければ tournaments.jsonl の記録パスとの一致から event_id を探す。"""
    try:
        attr = read_json(str(event_dir / "attr.json"))
        event_id = attr.get("event_id")
        if event_id is not None:
            return event_id
    except (OSError, ValueError):
        pass
    target = str(event_dir)
    for tournament in tournaments.values():
        for event in tournament.get("events", []):
            if event.get("path") == target:
                return event.get("event_id")
    return None


def resolve_tournament_id(event_id: int | None, event_dir: Path, tournaments: dict) -> int | None:
    """event_id または保存先パスの一致から、この event が属する tournament_id を探す。"""
    target = str(event_dir)
    for tournament_id, tournament in tournaments.items():
        for event in tournament.get("events", []):
            if event.get("path") == target or (event_id is not None and event.get("event_id") == event_id):
                return tournament_id
    return None


def has_unrecorded_sibling_event(tournament_id: int, game_id: str, tournaments: dict) -> bool | None:
    """tournament_id 配下に、tournaments.jsonl にまだ記録されていない(対象ゲームの)
    event_id が存在するかどうかを確認する。API側で確認できなかった場合は None を返す
    (呼び出し元は None を「安全側に倒して削除しない」として扱うこと)。"""
    known_ids = {e.get("event_id") for e in tournaments.get(tournament_id, {}).get("events", [])}
    try:
        events_info = fetch_event_ids_from_tournament(tournament_id, game_id)
    except FetchError as exc:
        print(f"[{tournament_id}] sibling check failed, treating as unresolved: {exc}", file=sys.stderr)
        return None
    return any(event_id not in known_ids for event_id, _name, _online in events_info)


def reconcile_empty_event(
    event_dir: Path,
    tournaments: dict,
    users: dict,
    users_file_path: str,
    game_id: str,
) -> str:
    """1件の空イベント候補を確認し、"healed" | "deleted" | "kept" のいずれかを返す。

    - healed: 再取得の結果、実データが見つかり保存した(削除しない)
    - deleted: 再取得後も空で、トーナメント配下に他のイベントも無いことを確認できたため削除した
    - kept: 判断がつかない、または他に確認すべきイベントがあるため何もしなかった
    """
    event_id = resolve_event_id(event_dir, tournaments)
    if event_id is None:
        print(f"[{event_dir}] event_id を特定できないため保留します。", file=sys.stderr)
        return "kept"

    tournament_id = resolve_tournament_id(event_id, event_dir, tournaments)

    # 1. 同じ event_id を直接再取得する。
    backfill_one_event(event_dir, users, users_file_path, tournaments=tournaments)
    if not is_empty_event(event_dir):
        print(f"[{event_id}] 再取得で実データが見つかりました。保存して削除は行いません: {event_dir}")
        return "healed"

    # 2. トーナメント配下に他のイベントが無いか確認する。
    if tournament_id is None:
        print(f"[{event_dir}] tournament_id を特定できないため保留します。", file=sys.stderr)
        return "kept"

    sibling_exists = has_unrecorded_sibling_event(tournament_id, game_id, tournaments)
    if sibling_exists is None:
        print(f"[{tournament_id}] 他のイベントの有無を確認できないため保留します。", file=sys.stderr)
        return "kept"
    if sibling_exists:
        print(f"[{tournament_id}] 未記録の他のイベントが見つかったため、この空イベントの削除は保留します: {event_dir}")
        return "kept"

    # 3. 再取得後も空で、他のイベントも確認できなかった場合のみ削除する。
    shutil.rmtree(event_dir)
    print(f"Deleted empty event directory (confirmed still empty on start.gg): {event_dir}")
    return "deleted"


def prune_empty_events(
    events_root: Path,
    tournament_file_path: str,
    users_file_path: str,
    game_id: str,
    apply: bool,
) -> dict:
    """空のイベントディレクトリ候補を検出し、apply=True の場合のみ start.gg への
    再確認を行った上で削除・自動修復する。

    {"found": int, "healed": int, "deleted": int, "kept": int, "deleted_paths": list[str]}
    """
    empty_dirs = find_empty_event_dirs(events_root)
    result = {"found": len(empty_dirs), "healed": 0, "deleted": 0, "kept": 0, "deleted_paths": []}

    if not empty_dirs:
        return result

    if not apply:
        for event_dir in empty_dirs:
            print(f"[DRY-RUN] would verify (and possibly delete) empty event directory: {event_dir}")
        return result

    tournaments = read_tournaments_jsonl(tournament_file_path)
    users = read_users_jsonl(users_file_path)

    deleted_paths = []
    changed = False
    for event_dir in empty_dirs:
        outcome = reconcile_empty_event(event_dir, tournaments, users, users_file_path, game_id)
        if outcome == "healed":
            result["healed"] += 1
            changed = True
        elif outcome == "deleted":
            result["deleted"] += 1
            deleted_paths.append(str(event_dir))
            changed = True
        else:
            result["kept"] += 1

    if deleted_paths:
        deleted_set = set(deleted_paths)
        for tournament in tournaments.values():
            tournament["events"] = [
                e for e in tournament.get("events", []) if e.get("path") not in deleted_set
            ]

    if changed:
        write_jsonl(list(tournaments.values()), tournament_file_path, with_version=True)

    result["deleted_paths"] = sorted(deleted_paths)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify (against start.gg) and delete event directories confirmed to still "
        "have no standings/matches data."
    )
    parser.add_argument("--token", required=True, help="start.gg API token")
    parser.add_argument("--events_root", default="data/startgg/events", help="Events root directory")
    parser.add_argument(
        "--tournament_file_path",
        default="data/startgg/tournaments.jsonl",
        help="Path to tournaments.jsonl (only read/updated when --apply is set)",
    )
    parser.add_argument("--users_file_path", default="data/startgg/users.jsonl", help="Path to users.jsonl")
    parser.add_argument("--game_id", default="1386", help="Game ID used for the sibling-event check.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually verify against start.gg and delete/heal directories. "
        "Without this flag, only reports how many candidates were found (no API calls).",
    )
    parser.add_argument("--url", default="https://api.start.gg/gql/alpha", help="API URL")
    parser.add_argument("--max_retries", type=int, default=20, help="Maximum number of retries for API requests")
    parser.add_argument("--retry_delay", type=int, default=5, help="Delay between retries in seconds")
    parser.add_argument("--indent_num", type=int, default=2, help="Indentation level for JSON output")
    args = parser.parse_args()

    set_indent_num(args.indent_num)
    set_retry_parameters(args.max_retries, args.retry_delay)
    set_api_parameters(args.url, args.token)

    summary = prune_empty_events(
        Path(args.events_root), args.tournament_file_path, args.users_file_path, args.game_id, args.apply,
    )

    print(
        f"Done. found={summary['found']} healed={summary['healed']} "
        f"deleted={summary['deleted']} kept={summary['kept']} apply={str(args.apply).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
