import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import labeling


def _write_rules(path: Path, ruleset: dict) -> None:
    path.write_text(json.dumps(ruleset, ensure_ascii=False), encoding="utf-8")


class LoadAndCompileTests(unittest.TestCase):
    """T006/T009: ルール定義ファイルの読み込み・検証。"""

    def test_missing_file_raises_label_rule_error(self):
        with self.assertRaises(labeling.LabelRuleError):
            labeling.load_label_ruleset("/nonexistent/path/label_rules.json")

    def test_invalid_json_raises_label_rule_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "label_rules.json"
            path.write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(labeling.LabelRuleError):
                labeling.load_label_ruleset(str(path))

    def test_missing_label_version_raises(self):
        with self.assertRaises(labeling.LabelRuleError):
            labeling.compile_label_ruleset({"matches": []})

    def test_missing_matches_raises(self):
        with self.assertRaises(labeling.LabelRuleError):
            labeling.compile_label_ruleset({"label_version": 1})

    def test_rule_missing_label_raises(self):
        with self.assertRaises(labeling.LabelRuleError):
            labeling.compile_label_ruleset(
                {"label_version": 1, "matches": [{"tournament_name_match": "foo"}]}
            )

    def test_rule_missing_both_matchers_raises(self):
        with self.assertRaises(labeling.LabelRuleError):
            labeling.compile_label_ruleset({"label_version": 1, "matches": [{"label": "x"}]})

    def test_invalid_regex_raises(self):
        with self.assertRaises(labeling.LabelRuleError):
            labeling.compile_label_ruleset(
                {"label_version": 1, "matches": [{"label": "x", "tournament_name_match": "("}]}
            )

    def test_multiple_problems_reported_together(self):
        with self.assertRaises(labeling.LabelRuleError) as ctx:
            labeling.compile_label_ruleset(
                {
                    "matches": [
                        {"label": "x", "tournament_name_match": "("},
                        {"tournament_name_match": "foo"},
                    ]
                }
            )
        message = str(ctx.exception)
        self.assertIn("label_version", message)
        self.assertIn("不正な正規表現", message)
        self.assertIn("label が存在しない", message)

    def test_slash_and_bare_pattern_equivalent(self):
        with_slashes = labeling.compile_label_ruleset(
            {"label_version": 1, "matches": [{"label": "restricted", "tournament_name_match": "/制限/"}]}
        )
        without_slashes = labeling.compile_label_ruleset(
            {"label_version": 1, "matches": [{"label": "restricted", "tournament_name_match": "制限"}]}
        )
        self.assertEqual(
            labeling.compute_labels(with_slashes, "第1回制限大会", None),
            labeling.compute_labels(without_slashes, "第1回制限大会", None),
        )


class ComputeLabelsTests(unittest.TestCase):
    """T007/T009/T021 (US3): AND/OR条件・複数ラベル同時付与。"""

    def setUp(self):
        self.compiled = labeling.compile_label_ruleset(
            {
                "label_version": 3,
                "matches": [
                    {"label": "registration_restricted", "tournament_name_match": "/制限/"},
                    {"label": "registration_restricted", "event_name_match": "/制限/"},
                    {"label": "casual", "tournament_name_match": "/スマパ/", "event_name_match": "/カジュアル/"},
                ],
            }
        )

    def test_tournament_name_match_only(self):
        labels = labeling.compute_labels(self.compiled, "第1回制限大会", "Singles")
        self.assertEqual(labels, {"registration_restricted": True})

    def test_event_name_match_only(self):
        labels = labeling.compute_labels(self.compiled, "第1回大会", "制限Singles")
        self.assertEqual(labels, {"registration_restricted": True})

    def test_or_condition_across_rules_for_same_label(self):
        # tournament条件のみで成立するケース(上と同じだが明示的に確認)
        labels = labeling.compute_labels(self.compiled, "制限大会", "Singles")
        self.assertTrue(labels.get("registration_restricted"))

    def test_and_condition_requires_both(self):
        only_tournament = labeling.compute_labels(self.compiled, "スマパ", "Singles")
        only_event = labeling.compute_labels(self.compiled, "通常大会", "カジュアル")
        both = labeling.compute_labels(self.compiled, "スマパ", "カジュアルSingles")
        self.assertNotIn("casual", only_tournament)
        self.assertNotIn("casual", only_event)
        self.assertTrue(both.get("casual"))

    def test_no_match_yields_no_keys(self):
        labels = labeling.compute_labels(self.compiled, "通常大会", "通常イベント")
        self.assertEqual(labels, {})

    def test_independent_labels_can_both_be_true(self):
        labels = labeling.compute_labels(self.compiled, "制限スマパ", "カジュアル")
        self.assertTrue(labels.get("registration_restricted"))
        self.assertTrue(labels.get("casual"))

    def test_none_tournament_and_event_name_do_not_error(self):
        labels = labeling.compute_labels(self.compiled, None, None)
        self.assertEqual(labels, {})


class MergeLabelsTests(unittest.TestCase):
    """T007/T009: 管理対象外キーの保持、管理対象キーの完全置き換え。"""

    def test_preserves_unmanaged_keys_and_replaces_managed_keys(self):
        existing = {"registration_type": "full-open", "registration_restricted": True}
        computed = {}  # 今回は不一致
        merged = labeling.merge_labels(existing, computed, frozenset({"registration_restricted", "casual"}))
        self.assertEqual(merged, {"registration_type": "full-open"})

    def test_none_existing_labels(self):
        merged = labeling.merge_labels(None, {"x": True}, frozenset({"x"}))
        self.assertEqual(merged, {"x": True})


class ComputeEventLabelsTests(unittest.TestCase):
    """T008/T009/T022 (US4): label_version付与・min_event_data_versionゲート・キャッシュ。"""

    def setUp(self):
        labeling._load_compiled_ruleset.cache_clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.rules_path = str(Path(self._tmp.name) / "label_rules.json")

    def tearDown(self):
        labeling._load_compiled_ruleset.cache_clear()
        self._tmp.cleanup()

    def test_returns_merged_labels_and_label_version(self):
        _write_rules(
            Path(self.rules_path),
            {"label_version": 5, "matches": [{"label": "restricted", "tournament_name_match": "制限"}]},
        )
        labels, label_version = labeling.compute_event_labels(
            {"registration_type": "full-open"}, "制限大会", "Singles", 7, rules_path=self.rules_path
        )
        self.assertEqual(labels, {"registration_type": "full-open", "restricted": True})
        self.assertEqual(label_version, 5)

    def test_ruleset_loaded_once_per_rules_path(self):
        _write_rules(Path(self.rules_path), {"label_version": 1, "matches": []})
        with patch.object(labeling, "load_label_ruleset", wraps=labeling.load_label_ruleset) as spy:
            labeling.compute_event_labels(None, "T", "E", 1, rules_path=self.rules_path)
            labeling.compute_event_labels(None, "T2", "E2", 1, rules_path=self.rules_path)
            labeling.compute_event_labels(None, "T3", "E3", 1, rules_path=self.rules_path)
        self.assertEqual(spy.call_count, 1)

    def test_min_event_data_version_gate_skips_and_preserves_existing(self):
        _write_rules(
            Path(self.rules_path),
            {
                "label_version": 2,
                "min_event_data_version": 5,
                "matches": [{"label": "restricted", "tournament_name_match": "制限"}],
            },
        )
        existing = {"registration_type": "full-open"}
        labels, label_version = labeling.compute_event_labels(
            existing, "制限大会", "Singles", 4, rules_path=self.rules_path
        )
        self.assertEqual(labels, existing)
        self.assertIsNone(label_version)

    def test_missing_event_data_version_treated_as_zero(self):
        _write_rules(
            Path(self.rules_path),
            {"label_version": 2, "min_event_data_version": 1, "matches": []},
        )
        labels, label_version = labeling.compute_event_labels(
            {"k": "v"}, "T", "E", None, rules_path=self.rules_path
        )
        self.assertEqual(labels, {"k": "v"})
        self.assertIsNone(label_version)

    def test_no_min_event_data_version_applies_to_all_versions(self):
        _write_rules(
            Path(self.rules_path),
            {"label_version": 2, "matches": [{"label": "restricted", "tournament_name_match": "制限"}]},
        )
        labels, label_version = labeling.compute_event_labels(
            None, "制限大会", "Singles", None, rules_path=self.rules_path
        )
        self.assertEqual(labels, {"restricted": True})
        self.assertEqual(label_version, 2)


if __name__ == "__main__":
    unittest.main()
