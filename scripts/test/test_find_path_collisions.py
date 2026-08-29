import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.fix import find_path_collisions as fpc


class FindPathCollisionsTests(unittest.TestCase):
    def _write_tournaments(self, path: Path, entries):
        with path.open("w", encoding="utf-8") as f:
            for entry in entries:
                json.dump(entry, f, ensure_ascii=False)
                f.write("\n")

    def _run_main(self, tournaments_file: Path):
        argv = ["find_path_collisions.py", "--tournaments-file", str(tournaments_file)]
        buf = io.StringIO()
        with patch.object(fpc.sys, "argv", argv), redirect_stdout(buf):
            exit_code = fpc.main()
        return exit_code, buf.getvalue()

    def test_reports_collision_between_distinct_tournament_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file = Path(tmpdir) / "tournaments.jsonl"
            self._write_tournaments(
                tournaments_file,
                [
                    {
                        "tournament_id": 1,
                        "name": "T",
                        "events": [{"event_id": 10, "event_name": "Singles", "path": "a/b/T/Singles"}],
                    },
                    {
                        "tournament_id": 2,
                        "name": "T",
                        "events": [{"event_id": 20, "event_name": "Singles", "path": "a/b/T/Singles"}],
                    },
                ],
            )

            exit_code, output = self._run_main(tournaments_file)

            self.assertEqual(exit_code, 0)
            self.assertIn("1件の保存先パス衝突", output)
            self.assertIn("tournament_id=1", output)
            self.assertIn("tournament_id=2", output)

    def test_reports_nothing_when_no_collision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file = Path(tmpdir) / "tournaments.jsonl"
            self._write_tournaments(
                tournaments_file,
                [
                    {
                        "tournament_id": 1,
                        "name": "T",
                        "events": [{"event_id": 10, "event_name": "Singles", "path": "a/b/T/Singles"}],
                    },
                    {
                        "tournament_id": 2,
                        "name": "U",
                        "events": [{"event_id": 20, "event_name": "Singles", "path": "a/b/U/Singles"}],
                    },
                ],
            )

            exit_code, output = self._run_main(tournaments_file)

            self.assertEqual(exit_code, 0)
            self.assertIn("見つかりませんでした", output)

    def test_does_not_report_multiple_events_of_the_same_tournament(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file = Path(tmpdir) / "tournaments.jsonl"
            self._write_tournaments(
                tournaments_file,
                [
                    {
                        "tournament_id": 1,
                        "name": "T",
                        "events": [
                            {"event_id": 10, "event_name": "Singles", "path": "a/b/T/Singles"},
                            {"event_id": 11, "event_name": "Doubles", "path": "a/b/T/Doubles"},
                        ],
                    },
                ],
            )

            exit_code, output = self._run_main(tournaments_file)

            self.assertEqual(exit_code, 0)
            self.assertIn("見つかりませんでした", output)


if __name__ == "__main__":
    unittest.main()
