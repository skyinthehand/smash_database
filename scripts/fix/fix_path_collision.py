#!/usr/bin/env python3
"""Repair a detected path collision between two or more event_ids (specs/008-
tournament-path-collision, User Story 4).

`scripts/fix/find_path_collisions.py` が報告した衝突のうち、指定したevent_id群
(同一の同日同名グループに属する2件以上)を対象に分離する。

衝突している対象同士は、実際には同一の物理ディレクトリを共有しており、衝突発生の
仕組み上、後から取得された側が無条件に上書きするため、生存しているのはどちらか
片方のevent_idの実データだけである(もう片方は既に上書きされて消滅している)。

ローカルの `attr.json` の `event_id` フィールドだけでは「今どちらのevent_idの
データか」を確実には判定できない: `matches.json` の逐次取得が未完了のまま中断
した場合(still_incomplete)、`write_event_attributes()` が呼ばれず
`standings.json` だけが新しいイベントのもので上書きされ、`attr.json` だけ古い
イベントの情報が残る、という状態になり得るためである。そのため本ツールは、
各対象event_idについて **start.ggへ直接アクセスして参加者数を取得し直し**、
最も参加者数が多い1件を「勝者」として無条件に確定させる(同数の場合は
tournament_idが小さい方を勝者とする)。勝者は`redownload_event.py`と同様の
手順で改めて完全に再取得して本来の(衝突していた)保存先へ書き込み、それ以外の
(敗者)対象は`tournaments.jsonl`の登録を削除するのみとする。

安全のため、敗者側は再取得した参加者数が **必ず0** であることを要求する。
0でない敗者が1件でもあれば、単純なテスト大会ではない可能性があるとして
自動実行を中止する(手動確認を促す)。

ただし、`data/startgg/excluded_events.json`(`load_excluded_event_ids()`)に
グループ内のちょうど1件だけが登録されている場合は、その1件を無条件に敗者、
残りの1件を無条件に勝者とする(目視確認済みの人間の判断を、参加者数比較
より優先する)。この場合、敗者側の参加者数が0であることは要求しない
(除外理由が「全員ゲスト」等、参加者数が0でないケースもあり得るため)。

`--yes` が無ければ、start.ggへの参加者数取得は行うが、実際の変更(ディレクトリの
書き込み・`tournaments.jsonl`の更新)は一切行わない(FR-009/FR-010)。

対象のevent_idは`--event-id`で明示的に指定する他、`--all`を指定すると
`find_path_collisions.py`と同じロジックで`tournaments.jsonl`内の衝突を自動的に
洗い出し、見つかった衝突グループすべてに対して(1グループずつ)同じ処理を行う。
1グループで安全確認に失敗しても他のグループの処理は継続し、最後にまとめて
`tournaments.jsonl`を更新する。

使い方:
    # まずは確認のみ(start.ggから参加者数を取得し直して比較するが、変更はしない)
    python3 scripts/fix/fix_path_collision.py --token <TOKEN> --event-id 1642641 1620892

    # 実際に修復する(3件以上もまとめて指定できる)
    python3 scripts/fix/fix_path_collision.py --token <TOKEN> --event-id 1642641 1620892 1700000 --yes

    # tournaments.jsonl内の衝突を自動的に洗い出して、まとめて確認・修復する
    python3 scripts/fix/fix_path_collision.py --token <TOKEN> --all
    python3 scripts/fix/fix_path_collision.py --token <TOKEN> --all --yes
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

ROOT_DIR = str(Path(__file__).resolve().parents[2])
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.fetch.download import (  # noqa: E402
    count_guest_entrants,
    download_all_set,
    download_seeds,
    download_standings,
    load_excluded_event_ids,
    write_event_attributes,
)
from scripts.fix.find_path_collisions import find_collisions, group_events_by_path  # noqa: E402
from scripts.fix.redownload_event import build_place_dict, fetch_event_details  # noqa: E402
from scripts.utils import (  # noqa: E402
    FetchError,
    NoPhaseError,
    get_date_parts,
    get_event_directory,
    set_api_parameters,
    set_indent_num,
    set_retry_parameters,
)

DEFAULT_TOURNAMENTS = Path("data/startgg/tournaments.jsonl")
DEFAULT_EVENTS_ROOT = Path("data/startgg/events")
JSON_VERSION = "1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair a path collision between two or more event_ids reported by "
            "find_path_collisions.py, using live participant counts from start.gg."
        )
    )
    parser.add_argument(
        "--event-id",
        type=int,
        nargs="+",
        default=None,
        help="event_id(s) sharing the colliding path (2 or more). Mutually exclusive with --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Auto-discover every path collision in tournaments.jsonl (same logic as "
            "find_path_collisions.py) and process each group. Mutually exclusive with --event-id."
        ),
    )
    parser.add_argument("--token", required=True, help="start.gg API token")
    parser.add_argument("--url", default="https://api.start.gg/gql/alpha", help="API URL")
    parser.add_argument("--max-retries", type=int, default=20, help="Maximum number of retries for API requests")
    parser.add_argument("--retry-delay", type=int, default=5, help="Delay between retries in seconds")
    parser.add_argument("--indent-num", type=int, default=2, help="Indentation level for JSON output")
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
        help="Actually redownload the winner and update tournaments.jsonl. Without this flag, only a preview is shown.",
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
        self.registered_path = Path(event_entry["path"])
        self.event_details: Optional[dict] = None
        self.tournament_details: Optional[dict] = None
        self.naive_path: Optional[Path] = None
        self.fetch_failed = False
        self.num_entrants: Optional[int] = None
        self.excluded = False


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


def resolve_targets(event_ids: List[int], tournaments: List[dict]) -> List[Target]:
    index = build_event_index(tournaments)
    targets = []
    for event_id in event_ids:
        if event_id not in index:
            raise RuntimeError(f"event_id={event_id} は tournaments.jsonl に見つかりません。")
        tournament_id, tournament_entry, event_entry = index[event_id]
        targets.append(Target(event_id, tournament_id, tournament_entry, event_entry))
    return targets


def fetch_naive_path(target: Target, events_root: Path) -> None:
    """start.ggからevent/tournamentの詳細を取得し、素直な(衝突しうる)保存先パスを
    計算する。start.gg側でイベント自体が既に見つからない場合(削除済み等)は
    fetch_failed=True とし、参加者数0・実データなしとして扱う。"""
    try:
        event, tournament = fetch_event_details(target.event_id)
    except FetchError as exc:
        print(f"[{target.event_id}] start.ggから詳細を取得できません(削除済みの可能性): {exc}", file=sys.stderr)
        target.fetch_failed = True
        target.num_entrants = 0
        return

    target.event_details = event
    target.tournament_details = tournament
    tournament_name = tournament.get("name") or "Unknown Tournament"
    event_name = event.get("name") or "Unknown Event"
    timestamp = event.get("startAt") or tournament.get("startAt")
    if timestamp is None:
        raise RuntimeError(f"event_id={target.event_id}: start.ggからtimestampを取得できません。")
    country_code = tournament.get("countryCode") or ""
    year, month, day = get_date_parts(timestamp)
    target.naive_path = Path(
        get_event_directory(str(events_root), country_code, year, month, day, tournament_name, event_name)
    )


def probe_num_entrants(target: Target, scratch_dir: Path) -> None:
    """start.ggから改めてstandingsを取得し、現時点の真の参加者数を得る
    (ローカルファイルのattr.json/num_entrantsは信頼しない)。"""
    if target.fetch_failed:
        return
    user_data, _player_data, _entrant2user = download_standings(target.event_id, str(scratch_dir))
    target.num_entrants = len(user_data)


def redownload_winner(winner: Target, events_root: Path) -> None:
    """勝者をredownload_event.py相当の手順で完全に再取得し、naive_pathへ書き込む
    (既存の内容は破棄する)。"""
    if winner.naive_path.is_dir():
        shutil.rmtree(winner.naive_path)
    os.makedirs(winner.naive_path, exist_ok=True)

    user_data, player_data, entrant2user = download_standings(winner.event_id, str(winner.naive_path))
    num_entrants = len(user_data)
    try:
        download_seeds(winner.event_id, user_data, player_data, entrant2user, str(winner.naive_path))
    except NoPhaseError as exc:
        print(f"[{winner.event_id}] seeds not available: {exc}", file=sys.stderr)
    download_all_set(winner.event_id, entrant2user, str(winner.naive_path))

    place = build_place_dict(winner.tournament_details)
    write_event_attributes(
        num_entrants,
        winner.event_id,
        winner.event_details.get("name") or "Unknown Event",
        winner.tournament_details.get("name") or "Unknown Tournament",
        winner.event_details.get("startAt") or winner.tournament_details.get("startAt"),
        place,
        winner.tournament_details.get("url"),
        {},
        winner.event_details.get("isOnline"),
        str(winner.naive_path),
        guest_entrant_count=count_guest_entrants(user_data),
        end_at=winner.tournament_details.get("endAt"),
        state=winner.event_details.get("state"),
        event_type=winner.event_details.get("type"),
    )
    winner.event_entry["path"] = str(winner.naive_path)


def process_group(
    event_ids: List[int], tournaments: List[dict], events_root: Path, yes: bool,
    excluded_event_ids: Optional[Dict[int, dict]] = None,
) -> tuple[bool, List[int]]:
    """1つの衝突グループ(event_id群)を処理する。

    excluded_event_ids(`data/startgg/excluded_events.json`由来、
    `load_excluded_event_ids()`の戻り値)に、このグループのうちちょうど1件だけが
    含まれる場合は、その1件を無条件に敗者、残りの1件を無条件に勝者とする
    (人間が既に目視確認した除外判断を、参加者数比較より優先する)。この場合、
    敗者側は参加者数が0であることを要求しない(除外理由が「全員ゲスト」等、
    参加者数が0でないケースもあり得るため)。
    それ以外(除外リストに複数、または1件も該当しない)の場合は、従来通り
    start.ggから取得し直した参加者数の比較で勝者を決める。

    戻り値: (success, emptied_tournament_ids)。success=Falseはエラー・安全確認
    失敗による中止(このグループへの変更は一切行われていない)。
    emptied_tournament_ids は yes=True かつ success=True の場合のみ意味を持つ
    (events が空になった tournament_id のリスト)。
    """
    excluded_event_ids = excluded_event_ids or {}
    try:
        targets = resolve_targets(event_ids, tournaments)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return False, []

    for target in targets:
        target.excluded = target.event_id in excluded_event_ids
        try:
            fetch_naive_path(target, events_root)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return False, []

    resolved_naive_paths = {str(t.naive_path) for t in targets if t.naive_path is not None}
    if len(resolved_naive_paths) > 1:
        details = "\n".join(f"  event_id={t.event_id}: {t.naive_path}" for t in targets if t.naive_path is not None)
        print(f"指定されたevent_idは同一の保存先パスに衝突していません:\n{details}", file=sys.stderr)
        return False, []
    if not resolved_naive_paths:
        print("指定された全event_idについてstart.ggから詳細を取得できませんでした。", file=sys.stderr)
        return False, []

    with tempfile.TemporaryDirectory() as scratch_root:
        for target in targets:
            scratch_dir = Path(scratch_root) / str(target.event_id)
            try:
                probe_num_entrants(target, scratch_dir)
            except FetchError as exc:
                print(f"[{target.event_id}] 参加者数の取得に失敗しました: {exc}", file=sys.stderr)
                return False, []

        excluded_targets = [t for t in targets if t.excluded]
        non_excluded_targets = [t for t in targets if not t.excluded]
        decision_by_exclusion = len(excluded_targets) >= 1 and len(non_excluded_targets) == 1

        if decision_by_exclusion:
            winner = non_excluded_targets[0]
            losers = excluded_targets
            decision_note = "(除外リストによる判定。参加者数比較は行わない)"
        else:
            winner = max(targets, key=lambda t: (t.num_entrants, -t.tournament_id))
            losers = [t for t in targets if t is not winner]
            decision_note = "(参加者数比較による判定)"

        non_zero_losers = [t for t in losers if not t.excluded and t.num_entrants != 0]

        print(f"対象(start.ggから取得し直した現在の参加者数) {decision_note}:")
        for target in targets:
            role = "維持(元の名前) [勝者]" if target is winner else "登録削除対象 [敗者]"
            if target.excluded:
                role += " [除外リスト登録済み]"
            outcome = str(winner.naive_path) if target is winner else "(tournaments.jsonlから登録を削除)"
            print(
                f"  event_id={target.event_id} tournament_id={target.tournament_id} "
                f"num_entrants={target.num_entrants}"
                f"{' (start.ggで見つからず)' if target.fetch_failed else ''}\n"
                f"    現在の登録パス: {target.registered_path}\n"
                f"    実行後: {outcome} [{role}]"
            )

        if non_zero_losers:
            details = ", ".join(f"event_id={t.event_id}(num_entrants={t.num_entrants})" for t in non_zero_losers)
            print(
                f"\n[ABORT] 敗者側に参加者数が0でない対象があります: {details}\n"
                "単純なテスト大会ではない可能性があるため、このグループの自動実行を中止します。"
                "手動で確認してください。",
                file=sys.stderr,
            )
            return False, []

        if not yes:
            print("\nDry-run only. Re-run with --yes to actually redownload the winner and update tournaments.jsonl.")
            return True, []

        redownload_winner(winner, events_root)

        emptied_tournament_ids = []
        for target in losers:
            events = target.tournament_entry.get("events", [])
            target.tournament_entry["events"] = [e for e in events if e is not target.event_entry]
            if not target.tournament_entry["events"]:
                emptied_tournament_ids.append(target.tournament_id)

        print(f"event_id={winner.event_id} を {winner.naive_path} へ再取得しました。")
        return True, emptied_tournament_ids


def main() -> int:
    args = parse_args()

    if bool(args.event_id) == bool(args.all):
        print("--event-id か --all のどちらか一方を指定してください。", file=sys.stderr)
        return 1

    if not args.tournaments_file.is_file():
        print(f"{args.tournaments_file} が見つかりません。", file=sys.stderr)
        return 1

    set_indent_num(args.indent_num)
    set_retry_parameters(args.max_retries, args.retry_delay)
    set_api_parameters(args.url, args.token)

    tournaments = load_tournaments(args.tournaments_file)
    excluded_event_ids = load_excluded_event_ids()

    if args.all:
        grouped = group_events_by_path(tournaments)
        collisions = find_collisions(grouped)
        if not collisions:
            print("保存先パスの衝突は見つかりませんでした。")
            return 0
        groups = [[member["event_id"] for member in members] for members in collisions.values()]
        print(f"{len(groups)}件の衝突グループが見つかりました。")
    else:
        if len(set(args.event_id)) < 2:
            print("--event-id には異なるevent_idを2件以上指定してください。", file=sys.stderr)
            return 1
        groups = [args.event_id]

    any_changed = False
    any_failed = False
    all_emptied_tournament_ids: List[int] = []
    for i, event_ids in enumerate(groups, start=1):
        if len(groups) > 1:
            print(f"\n=== グループ {i}/{len(groups)}: event_id={event_ids} ===")
        success, emptied_tournament_ids = process_group(
            event_ids, tournaments, args.events_root, args.yes, excluded_event_ids
        )
        if not success:
            any_failed = True
            continue
        if args.yes:
            any_changed = True
            all_emptied_tournament_ids.extend(emptied_tournament_ids)

    if any_changed:
        write_tournaments(tournaments, args.tournaments_file)
        print(f"\n{args.tournaments_file} を更新しました。")
        if all_emptied_tournament_ids:
            print(
                f"注意: tournament_id={all_emptied_tournament_ids} は events が空になりました。"
                "必要に応じて別途エントリ自体の削除を検討してください。"
            )

    if any_failed:
        print(
            "\n一部のグループは処理できませんでした(詳細は上記ログを参照)。他のグループへの"
            "変更は正常に反映されています。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
