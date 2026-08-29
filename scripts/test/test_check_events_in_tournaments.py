import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.fix import check_events_in_tournaments as cet


class CheckEventsInTournamentsExclusionTests(unittest.TestCase):
    """FR-006/US3: 除外リストに登録されたevent_idは「未登録」として報告されない。"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.events_root = self.root / "events"
        self.event_dir = self.events_root / "Japan" / "t1" / "e1"
        self.event_dir.mkdir(parents=True)
        with (self.event_dir / "attr.json").open("w", encoding="utf-8") as f:
            json.dump({"event_id": 999, "event_name": "Singles", "tournament_name": "T1"}, f)

        self.tournaments_file = self.root / "tournaments.jsonl"
        self.tournaments_file.write_text("", encoding="utf-8")

    def _run_main(self):
        argv = [
            "check_events_in_tournaments.py",
            "--tournaments-file", str(self.tournaments_file),
            "--events-root", str(self.events_root),
            "--repo-root", str(self.root),
        ]
        buf = io.StringIO()
        with patch.object(sys, "argv", argv), redirect_stdout(buf):
            exit_code = cet.main()
        return exit_code, buf.getvalue()

    def test_excluded_event_is_not_reported_as_missing(self):
        with patch.object(cet, "load_excluded_event_ids", return_value={999: {"reason": "test"}}):
            exit_code, output = self._run_main()

        self.assertEqual(exit_code, 0)
        self.assertIn("[SKIP-EXCLUDED]", output)
        self.assertNotIn("未登録", output)

    def test_non_excluded_event_is_still_reported_as_missing(self):
        with patch.object(cet, "load_excluded_event_ids", return_value={}):
            exit_code, output = self._run_main()

        self.assertEqual(exit_code, 1)
        self.assertIn("未登録", output)


if __name__ == "__main__":
    unittest.main()
