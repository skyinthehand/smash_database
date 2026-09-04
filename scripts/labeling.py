"""汎用イベントラベリング判定エンジン(specs/009-eligibility-restricted-labeling)。

`data/startgg/label_rules.json`(トーナメント名/イベント名に対する宣言的な正規表現
ルール)を読み込み・検証・コンパイルし、`attr.json` の `labels`/`label_version` を
算出する。start.gg への通信は一切行わない、ローカル完結の純粋なロジックである。

`scripts/fetch/download.py`・`scripts/fetch/download_specific_event.py`・
`scripts/fix/apply_label_rules.py` が共通で依存する(contracts/cli.md 参照)。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet, List, Optional, Tuple

DEFAULT_LABEL_RULES_PATH = "data/startgg/label_rules.json"


class LabelRuleError(Exception):
    """ルール定義ファイルの欠落・JSON不正・検証エラーをまとめて表す。"""


@dataclass
class CompiledLabelRule:
    label: str
    tournament_pattern: Optional["re.Pattern[str]"]
    event_pattern: Optional["re.Pattern[str]"]


@dataclass
class CompiledLabelRuleSet:
    label_version: int
    min_event_data_version: Optional[int]
    rules: List[CompiledLabelRule]
    managed_label_names: FrozenSet[str]


def _strip_slashes(pattern: str) -> str:
    """`/pattern/`記法の前後スラッシュを取り除く(research.md #2)。
    囲まれていない場合はそのまま返す。"""
    if len(pattern) >= 2 and pattern.startswith("/") and pattern.endswith("/"):
        return pattern[1:-1]
    return pattern


def load_label_ruleset(path: str = DEFAULT_LABEL_RULES_PATH) -> dict:
    """ルール定義ファイルを読み込みJSONとしてパースする。欠落・JSON不正の
    いずれも`LabelRuleError`にする(FR-012)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        raise LabelRuleError(f"ラベルルール定義ファイルが見つからないか読み込めません({path}): {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LabelRuleError(f"ラベルルール定義ファイルがJSONとして不正です({path}): {exc}") from exc


def compile_label_ruleset(ruleset: dict) -> CompiledLabelRuleSet:
    """ルール定義(dict)を検証し、正規表現コンパイル済みの`CompiledLabelRuleSet`を
    返す。検出した問題点はすべて列挙した1つの`LabelRuleError`にまとめて送出する
    (部分的な検証成功のまま処理を継続しない、research.md #3)。"""
    problems: List[str] = []

    if not isinstance(ruleset, dict):
        raise LabelRuleError("ラベルルール定義ファイルの内容がJSONオブジェクトではありません。")

    label_version = ruleset.get("label_version")
    if not isinstance(label_version, int) or isinstance(label_version, bool):
        problems.append("label_version が存在しないか整数ではありません。")

    min_event_data_version = ruleset.get("min_event_data_version")
    if min_event_data_version is not None and (
        not isinstance(min_event_data_version, int) or isinstance(min_event_data_version, bool)
    ):
        problems.append("min_event_data_version が整数でもnullでもありません。")

    matches = ruleset.get("matches")
    if not isinstance(matches, list):
        problems.append("matches が存在しないか配列ではありません。")
        matches = []

    compiled_rules: List[CompiledLabelRule] = []
    managed_label_names = set()
    for i, rule in enumerate(matches):
        if not isinstance(rule, dict):
            problems.append(f"matches[{i}] がオブジェクトではありません。")
            continue

        label = rule.get("label")
        if not isinstance(label, str) or not label:
            problems.append(f"matches[{i}].label が存在しないか文字列ではありません。")
            continue

        tournament_raw = rule.get("tournament_name_match")
        event_raw = rule.get("event_name_match")
        if tournament_raw is None and event_raw is None:
            problems.append(
                f"matches[{i}] ({label}): tournament_name_match/event_name_match の"
                "少なくとも一方を指定してください。"
            )
            continue

        rule_ok = True
        tournament_pattern = None
        if tournament_raw is not None:
            if not isinstance(tournament_raw, str):
                problems.append(f"matches[{i}] ({label}): tournament_name_match が文字列ではありません。")
                rule_ok = False
            else:
                try:
                    tournament_pattern = re.compile(_strip_slashes(tournament_raw))
                except re.error as exc:
                    problems.append(f"matches[{i}] ({label}): tournament_name_match が不正な正規表現です: {exc}")
                    rule_ok = False

        event_pattern = None
        if event_raw is not None:
            if not isinstance(event_raw, str):
                problems.append(f"matches[{i}] ({label}): event_name_match が文字列ではありません。")
                rule_ok = False
            else:
                try:
                    event_pattern = re.compile(_strip_slashes(event_raw))
                except re.error as exc:
                    problems.append(f"matches[{i}] ({label}): event_name_match が不正な正規表現です: {exc}")
                    rule_ok = False

        if not rule_ok:
            continue

        compiled_rules.append(
            CompiledLabelRule(label=label, tournament_pattern=tournament_pattern, event_pattern=event_pattern)
        )
        managed_label_names.add(label)

    if problems:
        details = "\n".join(f"- {p}" for p in problems)
        raise LabelRuleError(f"ラベルルール定義ファイルの検証に失敗しました:\n{details}")

    return CompiledLabelRuleSet(
        label_version=label_version,
        min_event_data_version=min_event_data_version,
        rules=compiled_rules,
        managed_label_names=frozenset(managed_label_names),
    )


def compute_labels(
    compiled: CompiledLabelRuleSet,
    tournament_name: Optional[str],
    event_name: Optional[str],
) -> dict:
    """一致したラベルのみを`True`で含むdictを返す(不一致ラベルはキー自体を
    含めない)。同じ`label`への複数ルールはOR条件、異なる`label`同士は独立
    (FR-002, FR-003)。"""
    result: dict = {}
    tournament_name = tournament_name or ""
    event_name = event_name or ""
    for rule in compiled.rules:
        if result.get(rule.label):
            continue
        tournament_ok = rule.tournament_pattern is None or bool(rule.tournament_pattern.search(tournament_name))
        event_ok = rule.event_pattern is None or bool(rule.event_pattern.search(event_name))
        if tournament_ok and event_ok:
            result[rule.label] = True
    return result


def merge_labels(
    existing_labels: Optional[dict],
    computed_labels: dict,
    managed_label_names: FrozenSet[str],
) -> dict:
    """`managed_label_names`に含まれない既存キーは保持し、含まれるキーは
    `computed_labels`で完全に置き換える(FR-006)。"""
    merged: dict = {}
    for key, value in (existing_labels or {}).items():
        if key not in managed_label_names:
            merged[key] = value
    merged.update(computed_labels)
    return merged


@lru_cache(maxsize=None)
def _load_compiled_ruleset(rules_path: str) -> CompiledLabelRuleSet:
    """`rules_path`ごとにプロセス内で1回だけ読み込み・検証・コンパイルする
    (research.md #3)。テストでキャッシュを無効化する場合は
    `_load_compiled_ruleset.cache_clear()` を呼ぶこと。"""
    ruleset = load_label_ruleset(rules_path)
    return compile_label_ruleset(ruleset)


def compute_event_labels(
    existing_labels: Optional[dict],
    tournament_name: Optional[str],
    event_name: Optional[str],
    event_data_version: Optional[int],
    *,
    rules_path: str = DEFAULT_LABEL_RULES_PATH,
) -> Tuple[dict, Optional[int]]:
    """1イベント分の`labels`/`label_version`を算出する。

    ルールセットの`min_event_data_version`要件を満たさない場合は判定の
    再計算自体を行わず`(existing_labels相当, None)`を返す(FR-011)。
    `event_data_version`が`None`の場合は`0`として扱う。
    """
    compiled = _load_compiled_ruleset(rules_path)

    effective_version = event_data_version if event_data_version is not None else 0
    if compiled.min_event_data_version is not None and effective_version < compiled.min_event_data_version:
        return (dict(existing_labels) if existing_labels else {}, None)

    computed = compute_labels(compiled, tournament_name, event_name)
    merged = merge_labels(existing_labels, computed, compiled.managed_label_names)
    return (merged, compiled.label_version)
