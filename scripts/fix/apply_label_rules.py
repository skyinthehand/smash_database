#!/usr/bin/env python3
"""既存の全イベントデータに、現在の `data/startgg/label_rules.json` を一括適用する
ツール(specs/009-eligibility-restricted-labeling, User Story 2)。

start.gg への再アクセスは一切行わず、既に保存されている `attr.json` の
`tournament_name`/`event_name` の値だけを使ってラベルを再判定し、`labels`/
`label_version` を更新する。デフォルトはdry-run(書き込みなし)で、`--yes`を
指定した場合のみ実際に`attr.json`へ書き込む(FR-007)。

使い方:
    # まずは確認のみ(dry-run、書き込みなし)
    python3 scripts/fix/apply_label_rules.py

    # 実際に書き込む
    python3 scripts/fix/apply_label_rules.py --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = str(Path(__file__).resolve().parents[2])
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.labeling import (  # noqa: E402
    LabelRuleError,
    compile_label_ruleset,
    compute_labels,
    load_label_ruleset,
    merge_labels,
)
from scripts.utils import read_json, set_indent_num, write_json  # noqa: E402

DEFAULT_EVENTS_ROOT = "data/startgg/events"
DEFAULT_RULES_FILE = "data/startgg/label_rules.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-apply the current label rules to all existing event attr.json files, "
            "without contacting start.gg."
        )
    )
    parser.add_argument(
        "--events-root",
        default=DEFAULT_EVENTS_ROOT,
        help=f"Root directory containing event folders (default: {DEFAULT_EVENTS_ROOT})",
    )
    parser.add_argument(
        "--rules-file",
        default=DEFAULT_RULES_FILE,
        help=f"Path to the label rules definition file (default: {DEFAULT_RULES_FILE})",
    )
    parser.add_argument("--indent-num", type=int, default=2, help="Indentation level for JSON output")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually write labels/label_version to attr.json. Without this flag, only a dry-run summary is shown.",
    )
    return parser.parse_args()


def process_events(events_root: Path, compiled, apply_changes: bool) -> dict:
    """`events_root`以下の全`attr.json`を走査し、判定結果を反映する(dry-runの
    場合は書き込まない)。結果のサマリーをdictで返す。"""
    updated = 0
    skipped_low_version = 0
    skipped_up_to_date = 0
    skipped_broken = 0

    for attr_path in sorted(events_root.rglob("attr.json")):
        try:
            attr = read_json(str(attr_path))
        except (OSError, ValueError) as exc:
            print(f"[WARN] {attr_path}: attr.jsonを読み込めません({exc})。スキップします。", file=sys.stderr)
            skipped_broken += 1
            continue

        event_id = attr.get("event_id")
        event_data_version = attr.get("event_data_version") or 0
        if (
            compiled.min_event_data_version is not None
            and event_data_version < compiled.min_event_data_version
        ):
            print(
                f"[{event_id}] skipped: event_data_version={event_data_version} が "
                f"min_event_data_version={compiled.min_event_data_version} 未満です ({attr_path})"
            )
            skipped_low_version += 1
            continue

        if attr.get("label_version") == compiled.label_version:
            skipped_up_to_date += 1
            continue

        computed = compute_labels(compiled, attr.get("tournament_name"), attr.get("event_name"))
        merged_labels = merge_labels(attr.get("labels"), computed, compiled.managed_label_names)
        attr["labels"] = merged_labels
        attr["label_version"] = compiled.label_version
        updated += 1

        prefix = "更新予定" if not apply_changes else "更新"
        print(f"[{event_id}] {prefix}: labels={merged_labels} label_version={compiled.label_version} ({attr_path})")

        if apply_changes:
            write_json(attr, str(attr_path), with_version=True)

    return {
        "updated": updated,
        "skipped_low_version": skipped_low_version,
        "skipped_up_to_date": skipped_up_to_date,
        "skipped_broken": skipped_broken,
    }


def main() -> int:
    args = parse_args()
    set_indent_num(args.indent_num)

    try:
        ruleset = load_label_ruleset(args.rules_file)
        compiled = compile_label_ruleset(ruleset)
    except LabelRuleError as exc:
        print(f"ラベルルール定義ファイルの読み込みに失敗しました: {exc}", file=sys.stderr)
        return 1

    summary = process_events(Path(args.events_root), compiled, args.yes)

    suffix = "" if args.yes else " (dry-run)"
    print(
        f"Done. updated={summary['updated']} skipped_low_version={summary['skipped_low_version']} "
        f"skipped_up_to_date={summary['skipped_up_to_date']} skipped_broken={summary['skipped_broken']}"
        f"{suffix}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
