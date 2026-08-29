import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.fix import fix_path_collision as fpc


class FixPathCollisionTests(unittest.TestCase):
    def _make_event(self, root: Path, region, tournament_name, event_name, tournament_id, event_id, num_entrants):
        event_dir = root / region / "2026" / "03" / "25" / tournament_name / event_name
        event_dir.mkdir(parents=True, exist_ok=True)
        with (event_dir / "attr.json").open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "event_id": event_id,
                    "tournament_name": tournament_name,
                    "event_name": event_name,
                    "place": {"country_code": "JP"},
                    "num_entrants": num_entrants,
                    "timestamp": 1774400000,
                },
                f,
            )
        with (event_dir / "marker.json").open("w", encoding="utf-8") as f:
            json.dump({"own": event_id}, f)
        return event_dir

    def _write_tournaments(self, path: Path, entries):
        with path.open("w", encoding="utf-8") as f:
            for entry in entries:
                json.dump(entry, f, ensure_ascii=False)
                f.write("\n")

    def _run_main(self, argv_tail):
        argv = ["fix_path_collision.py"] + argv_tail
        buf = io.StringIO()
        err = io.StringIO()
        with patch.object(fpc.sys, "argv", argv), redirect_stdout(buf), redirect_stderr(err):
            exit_code = fpc.main()
        return exit_code, buf.getvalue() + err.getvalue()

    def test_dry_run_makes_no_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_root = root / "events"
            dir_a = self._make_event(events_root, "Japan", "T", "Singles", 1, 10, num_entrants=3)
            dir_b = events_root / "Japan" / "2026" / "03" / "25" / "T_tmp" / "Singles"
            dir_b.mkdir(parents=True)
            with (dir_b / "attr.json").open("w", encoding="utf-8") as f:
                json.dump(
                    {
                        "event_id": 20, "tournament_name": "T", "event_name": "Singles",
                        "place": {"country_code": "JP"}, "num_entrants": 9, "timestamp": 1774400000,
                    },
                    f,
                )

            tournaments_file = root / "tournaments.jsonl"
            self._write_tournaments(
                tournaments_file,
                [
                    {"tournament_id": 1, "name": "T", "events": [{"event_id": 10, "event_name": "Singles", "path": str(dir_a)}]},
                    {"tournament_id": 2, "name": "T", "events": [{"event_id": 20, "event_name": "Singles", "path": str(dir_b)}]},
                ],
            )

            exit_code, output = self._run_main([
                "--tournaments-file", str(tournaments_file),
                "--events-root", str(events_root),
                "--event-id", "10", "20",
            ])

            self.assertEqual(exit_code, 0)
            self.assertIn("Dry-run only", output)
            self.assertTrue(dir_a.is_dir())
            self.assertTrue(dir_b.is_dir())
            with tournaments_file.open("r", encoding="utf-8") as f:
                self.assertIn(str(dir_a), f.read())

    def test_yes_separates_two_events_favoring_more_entrants(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_root = root / "events"
            # 両方とも(衝突を再現するため)同じnaiveパスに置く。
            dir_a = self._make_event(events_root, "Japan", "T", "Singles", 1, 10, num_entrants=3)
            dir_b = events_root / "Japan" / "2026" / "03" / "25" / "T_tmp" / "Singles"
            dir_b.mkdir(parents=True)
            with (dir_b / "attr.json").open("w", encoding="utf-8") as f:
                json.dump(
                    {
                        "event_id": 20, "tournament_name": "T", "event_name": "Singles",
                        "place": {"country_code": "JP"}, "num_entrants": 9, "timestamp": 1774400000,
                    },
                    f,
                )
            with (dir_b / "marker.json").open("w", encoding="utf-8") as f:
                json.dump({"own": 20}, f)

            tournaments_file = root / "tournaments.jsonl"
            self._write_tournaments(
                tournaments_file,
                [
                    {"tournament_id": 1, "name": "T", "events": [{"event_id": 10, "event_name": "Singles", "path": str(dir_a)}]},
                    {"tournament_id": 2, "name": "T", "events": [{"event_id": 20, "event_name": "Singles", "path": str(dir_b)}]},
                ],
            )

            exit_code, output = self._run_main([
                "--tournaments-file", str(tournaments_file),
                "--events-root", str(events_root),
                "--event-id", "10", "20",
                "--yes",
            ])

            self.assertEqual(exit_code, 0)
            naive_dir = events_root / "Japan" / "2026" / "03" / "25" / "T" / "Singles"
            loser_dir = events_root / "Japan" / "2026" / "03" / "25" / "T_(1)" / "Singles"

            self.assertEqual(json.loads((naive_dir / "attr.json").read_text(encoding="utf-8"))["event_id"], 20)
            self.assertEqual(json.loads((loser_dir / "attr.json").read_text(encoding="utf-8"))["event_id"], 10)

            with tournaments_file.open("r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            by_tid = {entry["tournament_id"]: entry for entry in lines}
            self.assertEqual(by_tid[2]["events"][0]["path"], str(naive_dir))
            self.assertEqual(by_tid[1]["events"][0]["path"], str(loser_dir))

    def test_yes_with_three_events_only_largest_keeps_clean_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_root = root / "events"
            dirs = {}
            counts = {10: 3, 20: 9, 30: 5}
            tids = {10: 1, 20: 2, 30: 3}
            for i, event_id in enumerate([10, 20, 30]):
                d = events_root / "Japan" / "2026" / "03" / "25" / f"T_tmp{i}" / "Singles"
                d.mkdir(parents=True)
                with (d / "attr.json").open("w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "event_id": event_id, "tournament_name": "T", "event_name": "Singles",
                            "place": {"country_code": "JP"}, "num_entrants": counts[event_id],
                            "timestamp": 1774400000,
                        },
                        f,
                    )
                dirs[event_id] = d

            tournaments_file = root / "tournaments.jsonl"
            self._write_tournaments(
                tournaments_file,
                [
                    {"tournament_id": tids[eid], "name": "T", "events": [{"event_id": eid, "event_name": "Singles", "path": str(dirs[eid])}]}
                    for eid in (10, 20, 30)
                ],
            )

            exit_code, _output = self._run_main([
                "--tournaments-file", str(tournaments_file),
                "--events-root", str(events_root),
                "--event-id", "10", "20", "30",
                "--yes",
            ])

            self.assertEqual(exit_code, 0)
            naive_dir = events_root / "Japan" / "2026" / "03" / "25" / "T" / "Singles"
            self.assertEqual(json.loads((naive_dir / "attr.json").read_text(encoding="utf-8"))["event_id"], 20)

            loser1_dir = events_root / "Japan" / "2026" / "03" / "25" / "T_(1)" / "Singles"
            loser3_dir = events_root / "Japan" / "2026" / "03" / "25" / "T_(3)" / "Singles"
            self.assertEqual(json.loads((loser1_dir / "attr.json").read_text(encoding="utf-8"))["event_id"], 10)
            self.assertEqual(json.loads((loser3_dir / "attr.json").read_text(encoding="utf-8"))["event_id"], 30)

    def test_rejects_single_event_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file = Path(tmpdir) / "tournaments.jsonl"
            tournaments_file.write_text("", encoding="utf-8")
            exit_code, output = self._run_main([
                "--tournaments-file", str(tournaments_file),
                "--event-id", "10",
            ])
            self.assertEqual(exit_code, 1)
            self.assertIn("2件以上", output)


if __name__ == "__main__":
    unittest.main()
