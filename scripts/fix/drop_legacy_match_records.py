#!/usr/bin/env python3
"""matches.json に残っている、set_id を持たない旧形式レコードを取り除くツール(issue #75)。

event_data_version 7 へのバックフィルでは、再取得した set_id 付きレコードが末尾に
追加される一方、set_id を持たない旧形式(event_data_version < 6)のレコードが
置き換えられずに残り、同じsetが二重に保存されていた。

start.gg への再アクセスは一切行わない。各 matches.json について、
`scripts.fetch.download.drop_superseded_legacy_records()` と同じ条件
(set_id 付きレコードが1件以上あり、プレースホルダーが1件も無い)を満たす場合のみ、
set_id を持たないレコードを取り除く。逐次取得の途中(プレースホルダーが残っている)
のイベントは対象外としてスキップする。

デフォルトは dry-run(書き込みなし)で、`--yes` を指定した場合のみ実際に書き込む。

使い方:
    # まずは確認のみ(dry-run、書き込みなし)
    python3 scripts/fix/drop_legacy_match_records.py

    # 対象ファイルを1件ずつ表示する
    python3 scripts/fix/drop_legacy_match_records.py --verbose

    # 実際に書き込む
    python3 scripts/fix/drop_legacy_match_records.py --yes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = str(Path(__file__).resolve().parents[2])
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.fetch.download import (  # noqa: E402
    drop_superseded_legacy_records,
    is_placeholder_record,
)
from scripts.utils import read_json, set_indent_num, write_json  # noqa: E402

DEFAULT_EVENTS_ROOT = "data/startgg/events"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Remove legacy match records without set_id from matches.json files "
            "whose sets have all been re-fetched with set_id, without contacting start.gg."
        )
    )
    parser.add_argument(
        "--events-root",
        default=DEFAULT_EVENTS_ROOT,
        help=f"Root directory containing event folders (default: {DEFAULT_EVENTS_ROOT})",
    )
    parser.add_argument("--indent-num", type=int, default=2, help="Indentation level for JSON output")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually rewrite matches.json. Without this flag, only a dry-run summary is shown.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print every file that would be updated.")
    return parser.parse_args()


def _content_key(record: dict) -> str:
    return json.dumps({k: v for k, v in record.items() if k != "set_id"}, sort_keys=True, ensure_ascii=False)


def process_events(events_root: Path, apply_changes: bool, verbose: bool = False) -> dict:
    """events_root 以下の全 matches.json を走査し、旧形式レコードを取り除く
    (dry-runの場合は書き込まない)。結果のサマリーを dict で返す。

    `removed_without_twin` は、取り除いた旧形式レコードのうち、set_id 以外の中身が
    完全一致する set_id 付きレコードが無かった件数(再取得で user_id の
    フォールバック解決などが変わったもの)。確認用の参考値。"""
    summary = {
        "files_scanned": 0,
        "files_updated": 0,
        "records_removed": 0,
        "removed_without_twin": 0,
        "skipped_incomplete": 0,
        "skipped_broken": 0,
    }

    for matches_path in sorted(events_root.rglob("matches.json")):
        summary["files_scanned"] += 1
        try:
            payload = read_json(str(matches_path))
        except (OSError, ValueError) as exc:
            print(f"[WARN] {matches_path}: matches.jsonを読み込めません({exc})。スキップします。", file=sys.stderr)
            summary["skipped_broken"] += 1
            continue

        data = payload.get("data") or []
        legacy = [record for record in data if record.get("set_id") is None]
        if not legacy or len(legacy) == len(data):
            continue

        cleaned = drop_superseded_legacy_records(data)
        if len(cleaned) == len(data):
            if any(is_placeholder_record(record) for record in data):
                summary["skipped_incomplete"] += 1
                print(f"[SKIP] {matches_path}: プレースホルダーが残っている(逐次取得の途中)ため対象外です。")
            continue

        twins = {_content_key(record) for record in cleaned}
        without_twin = sum(1 for record in legacy if _content_key(record) not in twins)

        summary["files_updated"] += 1
        summary["records_removed"] += len(data) - len(cleaned)
        summary["removed_without_twin"] += without_twin

        if verbose:
            prefix = "更新" if apply_changes else "更新予定"
            print(
                f"{prefix}: {matches_path} {len(data)} -> {len(cleaned)} 件"
                f" (中身が一致しない旧レコード {without_twin} 件)"
            )

        if apply_changes:
            payload["data"] = cleaned
            write_json(payload, str(matches_path), with_version=True)

    return summary


def main() -> int:
    args = parse_args()
    set_indent_num(args.indent_num)

    summary = process_events(Path(args.events_root), args.yes, args.verbose)

    suffix = "" if args.yes else " (dry-run)"
    print(
        f"Done. files_scanned={summary['files_scanned']} files_updated={summary['files_updated']} "
        f"records_removed={summary['records_removed']} "
        f"removed_without_twin={summary['removed_without_twin']} "
        f"skipped_incomplete={summary['skipped_incomplete']} "
        f"skipped_broken={summary['skipped_broken']}"
        f"{suffix}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
