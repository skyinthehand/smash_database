import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.fix import drop_legacy_match_records as dlm

LEGACY = {"winner_id": 11, "loser_id": 12, "winner_score": 2, "loser_score": 1}


def _write_matches(path: Path, data: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"data": data, "version": "1.0"}, ensure_ascii=False), encoding="utf-8")


def _read_matches(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))["data"]


class DropLegacyMatchRecordsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, apply_changes):
        with redirect_stdout(io.StringIO()):
            return dlm.process_events(self.root, apply_changes)

    def test_dry_run_does_not_write(self):
        path = self.root / "a" / "matches.json"
        original = [LEGACY, {"set_id": 1, **LEGACY}]
        _write_matches(path, original)

        summary = self._run(apply_changes=False)

        self.assertEqual(summary["files_updated"], 1)
        self.assertEqual(summary["records_removed"], 1)
        self.assertEqual(_read_matches(path), original)

    def test_apply_removes_legacy_records(self):
        path = self.root / "a" / "matches.json"
        changed = {**LEGACY, "winner_id": 99}  # 再取得でuser_idが変わった旧レコード
        _write_matches(path, [LEGACY, changed, {"set_id": 1, **LEGACY}, {"set_id": 2, **LEGACY, "round": 2}])

        summary = self._run(apply_changes=True)

        self.assertEqual(summary["records_removed"], 2)
        self.assertEqual(summary["removed_without_twin"], 1)
        self.assertEqual(
            _read_matches(path),
            [{"set_id": 1, **LEGACY}, {"set_id": 2, **LEGACY, "round": 2}],
        )

    def test_skips_events_with_placeholders(self):
        path = self.root / "a" / "matches.json"
        original = [LEGACY, {"set_id": 1, **LEGACY}, {"set_id": 2}]
        _write_matches(path, original)

        summary = self._run(apply_changes=True)

        self.assertEqual(summary["files_updated"], 0)
        self.assertEqual(summary["skipped_incomplete"], 1)
        self.assertEqual(_read_matches(path), original)

    def test_leaves_legacy_only_and_set_id_only_files_untouched(self):
        legacy_only = self.root / "a" / "matches.json"
        set_id_only = self.root / "b" / "matches.json"
        _write_matches(legacy_only, [LEGACY])
        _write_matches(set_id_only, [{"set_id": 1, **LEGACY}])

        summary = self._run(apply_changes=True)

        self.assertEqual(summary["files_scanned"], 2)
        self.assertEqual(summary["files_updated"], 0)
        self.assertEqual(_read_matches(legacy_only), [LEGACY])


if __name__ == "__main__":
    unittest.main()
