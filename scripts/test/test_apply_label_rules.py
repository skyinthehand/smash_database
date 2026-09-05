import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.fix import apply_label_rules as alr


RULES = {
    "label_version": 2,
    "matches": [{"label": "restricted", "tournament_name_match": "制限"}],
}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ApplyLabelRulesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.events_root = self.root / "events"
        self.rules_file = self.root / "label_rules.json"
        _write_json(self.rules_file, RULES)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self, extra_args=None, events_root=None, rules_file=None):
        argv = [
            "apply_label_rules.py",
            "--events-root", str(events_root or self.events_root),
            "--rules-file", str(rules_file or self.rules_file),
        ] + (extra_args or [])
        buf = io.StringIO()
        err = io.StringIO()
        with patch.object(alr.sys, "argv", argv), redirect_stdout(buf), redirect_stderr(err):
            exit_code = alr.main()
        return exit_code, buf.getvalue(), err.getvalue()

    def test_dry_run_does_not_write(self):
        event_dir = self.events_root / "e1"
        attr_path = event_dir / "attr.json"
        _write_json(attr_path, {"event_id": 1, "tournament_name": "制限大会", "event_name": "Singles"})

        exit_code, out, _err = self._run_main()

        self.assertEqual(exit_code, 0)
        self.assertIn("(dry-run)", out)
        self.assertIn("更新予定", out)
        attr = _read_json(attr_path)
        self.assertNotIn("label_version", attr)
        self.assertNotIn("labels", attr)

    def test_yes_actually_writes(self):
        event_dir = self.events_root / "e1"
        attr_path = event_dir / "attr.json"
        _write_json(attr_path, {"event_id": 1, "tournament_name": "制限大会", "event_name": "Singles"})

        exit_code, out, _err = self._run_main(["--yes"])

        self.assertEqual(exit_code, 0)
        self.assertNotIn("(dry-run)", out)
        attr = _read_json(attr_path)
        self.assertEqual(attr["labels"], {"restricted": True})
        self.assertEqual(attr["label_version"], 2)

    def test_broken_attr_json_is_skipped_and_others_continue(self):
        _write_json(self.events_root / "broken" / "attr.json", {})
        (self.events_root / "broken" / "attr.json").write_text("{not valid", encoding="utf-8")
        _write_json(
            self.events_root / "ok" / "attr.json",
            {"event_id": 2, "tournament_name": "制限大会", "event_name": "Singles"},
        )

        exit_code, out, err = self._run_main(["--yes"])

        self.assertEqual(exit_code, 0)
        self.assertIn("skipped_broken=1", out)
        self.assertIn("updated=1", out)
        self.assertIn("attr.json", err)
        attr = _read_json(self.events_root / "ok" / "attr.json")
        self.assertEqual(attr["label_version"], 2)

    def test_missing_attr_json_directory_is_skipped(self):
        # attr.json自体が存在しないディレクトリ(rglobの対象外になるだけ)でも
        # 他のディレクトリの処理に影響しないことを確認する。
        (self.events_root / "no_attr").mkdir(parents=True)
        _write_json(
            self.events_root / "ok" / "attr.json",
            {"event_id": 3, "tournament_name": "通常大会", "event_name": "Singles"},
        )
        exit_code, out, _err = self._run_main(["--yes"])
        self.assertEqual(exit_code, 0)
        self.assertIn("updated=1", out)

    def test_up_to_date_event_skips_recomputation(self):
        attr_path = self.events_root / "e1" / "attr.json"
        _write_json(
            attr_path,
            {
                "event_id": 1,
                "tournament_name": "制限大会",
                "event_name": "Singles",
                "labels": {"restricted": True},
                "label_version": 2,
            },
        )

        with patch.object(alr, "compute_labels") as mocked:
            exit_code, out, _err = self._run_main(["--yes"])

        mocked.assert_not_called()
        self.assertEqual(exit_code, 0)
        self.assertIn("skipped_up_to_date=1", out)
        self.assertIn("updated=0", out)

    def test_idempotent_second_yes_run_is_all_up_to_date(self):
        _write_json(
            self.events_root / "e1" / "attr.json",
            {"event_id": 1, "tournament_name": "制限大会", "event_name": "Singles"},
        )
        _write_json(
            self.events_root / "e2" / "attr.json",
            {"event_id": 2, "tournament_name": "通常大会", "event_name": "Singles"},
        )

        exit_code1, out1, _ = self._run_main(["--yes"])
        self.assertEqual(exit_code1, 0)
        self.assertIn("updated=2", out1)

        exit_code2, out2, _ = self._run_main(["--yes"])
        self.assertEqual(exit_code2, 0)
        self.assertIn("updated=0", out2)
        self.assertIn("skipped_up_to_date=2", out2)

    def test_no_api_related_functions_imported(self):
        """US2 Acceptance Scenario 2: start.ggへの通信は一切発生しない
        (関連するリトライ/API関数をimportすらしていないことを静的に確認する)。"""
        for name in ("fetch_data_with_retries", "fetch_all_nodes", "set_api_parameters", "set_retry_parameters"):
            self.assertFalse(hasattr(alr, name), f"{name} should not be imported by apply_label_rules")

    def test_rules_file_load_error_aborts_without_processing(self):
        broken_rules = self.root / "broken_rules.json"
        broken_rules.write_text("{not valid", encoding="utf-8")
        _write_json(
            self.events_root / "e1" / "attr.json",
            {"event_id": 1, "tournament_name": "制限大会", "event_name": "Singles"},
        )

        exit_code, _out, err = self._run_main(["--yes"], rules_file=broken_rules)

        self.assertEqual(exit_code, 1)
        self.assertTrue(err)
        attr = _read_json(self.events_root / "e1" / "attr.json")
        self.assertNotIn("label_version", attr)


class MinEventDataVersionTests(unittest.TestCase):
    """T023 (US4): min_event_data_versionによるスキップ・後日の再実行。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.events_root = self.root / "events"
        self.rules_file = self.root / "label_rules.json"
        _write_json(
            self.rules_file,
            {
                "label_version": 9,
                "min_event_data_version": 5,
                "matches": [{"label": "restricted", "tournament_name_match": "制限"}],
            },
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self, extra_args=None):
        argv = [
            "apply_label_rules.py",
            "--events-root", str(self.events_root),
            "--rules-file", str(self.rules_file),
        ] + (extra_args or [])
        buf = io.StringIO()
        err = io.StringIO()
        with patch.object(alr.sys, "argv", argv), redirect_stdout(buf), redirect_stderr(err):
            exit_code = alr.main()
        return exit_code, buf.getvalue(), err.getvalue()

    def test_low_version_event_is_skipped_and_unchanged(self):
        attr_path = self.events_root / "e1" / "attr.json"
        _write_json(
            attr_path,
            {"event_id": 1, "tournament_name": "制限大会", "event_name": "Singles", "event_data_version": 4},
        )

        exit_code, out, _err = self._run_main(["--yes"])

        self.assertEqual(exit_code, 0)
        self.assertIn("skipped_low_version=1", out)
        attr = _read_json(attr_path)
        self.assertNotIn("label_version", attr)
        self.assertNotIn("labels", attr)

    def test_reprocessed_once_version_requirement_met(self):
        attr_path = self.events_root / "e1" / "attr.json"
        _write_json(
            attr_path,
            {"event_id": 1, "tournament_name": "制限大会", "event_name": "Singles", "event_data_version": 4},
        )
        self._run_main(["--yes"])

        attr = _read_json(attr_path)
        attr["event_data_version"] = 5
        _write_json(attr_path, attr)

        exit_code, out, _err = self._run_main(["--yes"])
        self.assertEqual(exit_code, 0)
        self.assertIn("updated=1", out)
        attr = _read_json(attr_path)
        self.assertEqual(attr["label_version"], 9)
        self.assertEqual(attr["labels"], {"restricted": True})


class IgnoreLabelVersionOnlyTests(unittest.TestCase):
    """labelsの中身は変わらずlabel_versionだけが変わるイベントを、表示・書き込み
    対象から除外する `--ignore-label-version-only` の挙動。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.events_root = self.root / "events"
        self.rules_file = self.root / "label_rules.json"
        _write_json(self.rules_file, RULES)  # label_version=2, "制限"にマッチ

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self, extra_args=None):
        argv = [
            "apply_label_rules.py",
            "--events-root", str(self.events_root),
            "--rules-file", str(self.rules_file),
        ] + (extra_args or [])
        buf = io.StringIO()
        err = io.StringIO()
        with patch.object(alr.sys, "argv", argv), redirect_stdout(buf), redirect_stderr(err):
            exit_code = alr.main()
        return exit_code, buf.getvalue(), err.getvalue()

    def test_default_run_shows_and_writes_label_version_only_change(self):
        attr_path = self.events_root / "e1" / "attr.json"
        _write_json(
            attr_path,
            {
                "event_id": 1,
                "tournament_name": "制限大会",
                "event_name": "Singles",
                "labels": {"restricted": True},
                "label_version": 1,
            },
        )

        exit_code, out, _err = self._run_main(["--yes"])

        self.assertEqual(exit_code, 0)
        self.assertIn("[1]", out)
        self.assertIn("updated=1", out)
        self.assertIn("skipped_label_version_only=0", out)
        attr = _read_json(attr_path)
        self.assertEqual(attr["label_version"], 2)
        self.assertEqual(attr["labels"], {"restricted": True})

    def test_ignore_flag_skips_and_does_not_write_when_content_unchanged(self):
        attr_path = self.events_root / "e1" / "attr.json"
        original = {
            "event_id": 1,
            "tournament_name": "制限大会",
            "event_name": "Singles",
            "labels": {"restricted": True},
            "label_version": 1,
        }
        _write_json(attr_path, original)

        exit_code, out, _err = self._run_main(["--yes", "--ignore-label-version-only"])

        self.assertEqual(exit_code, 0)
        self.assertNotIn("[1]", out)
        self.assertIn("updated=0", out)
        self.assertIn("skipped_label_version_only=1", out)
        attr = _read_json(attr_path)
        self.assertEqual(attr, original)  # 完全に無変更(label_versionも古いまま)

    def test_ignore_flag_still_reports_real_content_changes(self):
        attr_path = self.events_root / "e1" / "attr.json"
        _write_json(
            attr_path,
            {
                "event_id": 1,
                "tournament_name": "制限大会",
                "event_name": "Singles",
                "labels": {},
                "label_version": 1,
            },
        )

        exit_code, out, _err = self._run_main(["--yes", "--ignore-label-version-only"])

        self.assertEqual(exit_code, 0)
        self.assertIn("[1]", out)
        self.assertIn("updated=1", out)
        self.assertIn("skipped_label_version_only=0", out)
        attr = _read_json(attr_path)
        self.assertEqual(attr["label_version"], 2)
        self.assertEqual(attr["labels"], {"restricted": True})

    def test_ignore_flag_dry_run_prints_nothing_for_skipped_event(self):
        attr_path = self.events_root / "e1" / "attr.json"
        _write_json(
            attr_path,
            {
                "event_id": 1,
                "tournament_name": "通常大会",
                "event_name": "Singles",
                "labels": {},
                "label_version": 1,
            },
        )

        exit_code, out, _err = self._run_main(["--ignore-label-version-only"])

        self.assertEqual(exit_code, 0)
        self.assertIn("(dry-run)", out)
        self.assertNotIn("[1]", out)
        self.assertIn("skipped_label_version_only=1", out)


if __name__ == "__main__":
    unittest.main()
