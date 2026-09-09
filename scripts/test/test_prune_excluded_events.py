import json
import os
import tempfile
import unittest
from unittest.mock import patch

from scripts.fix import prune_excluded_events as pee


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def _write_tournaments_jsonl(path, tournaments):
    with open(path, "w", encoding="utf-8") as f:
        for t in tournaments:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


class FindExcludedEventsInTournamentsTests(unittest.TestCase):
    def test_finds_event_matching_excluded_id(self):
        tournaments = {
            1: {
                "tournament_id": 1,
                "name": "T1",
                "events": [{"event_id": 10, "event_name": "E1", "path": "p1"}],
            }
        }

        found = pee.find_excluded_events_in_tournaments(tournaments, {10})

        self.assertEqual(found, [(1, 10, tournaments[1]["events"][0])])

    def test_ignores_non_excluded_event(self):
        tournaments = {
            1: {
                "tournament_id": 1,
                "name": "T1",
                "events": [{"event_id": 10, "event_name": "E1", "path": "p1"}],
            }
        }

        self.assertEqual([], pee.find_excluded_events_in_tournaments(tournaments, {999}))


class MainIntegrationTests(unittest.TestCase):
    def _setup(self, tmpdir, event_id=10, tournament_id=1, sibling=False, has_dir=True, phase_level=False):
        event_dir = os.path.join(tmpdir, f"event_{event_id}")
        if has_dir:
            os.makedirs(event_dir, exist_ok=True)
            with open(os.path.join(event_dir, "attr.json"), "w", encoding="utf-8") as f:
                f.write("{}")

        events = [{"event_id": event_id, "event_name": "E", "path": event_dir}]
        if sibling:
            sibling_dir = os.path.join(tmpdir, "sibling")
            os.makedirs(sibling_dir, exist_ok=True)
            events.append({"event_id": event_id + 1, "event_name": "Sibling", "path": sibling_dir})

        tournaments_file = os.path.join(tmpdir, "tournaments.jsonl")
        _write_tournaments_jsonl(
            tournaments_file,
            [{"tournament_id": tournament_id, "name": f"T{tournament_id}", "events": events}],
        )

        excluded_file = os.path.join(tmpdir, "excluded_events.json")
        if phase_level:
            _write_json(excluded_file, {str(event_id): [{"phase_id": 1, "reason": "test"}]})
        else:
            _write_json(excluded_file, {str(event_id): {"reason": "test"}})

        done_events_file = os.path.join(tmpdir, "done_events.csv")
        open(done_events_file, "w").close()

        return tournaments_file, excluded_file, done_events_file, event_dir

    def _run_main(self, tournaments_file, excluded_file, done_events_file, extra_args):
        argv = [
            "prune_excluded_events.py",
            "--tournaments-file", tournaments_file,
            "--excluded-events-file", excluded_file,
            "--done-events-file", done_events_file,
            *extra_args,
        ]
        with patch("sys.argv", argv):
            pee.main()

    def test_dry_run_does_not_modify_anything(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file, excluded_file, done_events_file, event_dir = self._setup(tmpdir)

            self._run_main(tournaments_file, excluded_file, done_events_file, [])

            self.assertTrue(os.path.isdir(event_dir))
            with open(tournaments_file, encoding="utf-8") as f:
                remaining = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(remaining), 1)

    def test_yes_removes_tournament_entry_and_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file, excluded_file, done_events_file, event_dir = self._setup(tmpdir)

            self._run_main(tournaments_file, excluded_file, done_events_file, ["--yes"])

            self.assertFalse(os.path.exists(event_dir))
            with open(tournaments_file, encoding="utf-8") as f:
                remaining = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(remaining, [])

    def test_yes_keeps_sibling_event_removes_only_excluded_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file, excluded_file, done_events_file, event_dir = self._setup(tmpdir, sibling=True)

            self._run_main(tournaments_file, excluded_file, done_events_file, ["--yes"])

            self.assertFalse(os.path.exists(event_dir))
            with open(tournaments_file, encoding="utf-8") as f:
                remaining = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(remaining), 1)
            self.assertEqual([e["event_id"] for e in remaining[0]["events"]], [11])

    def test_yes_does_not_error_when_directory_already_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file, excluded_file, done_events_file, event_dir = self._setup(tmpdir, has_dir=False)

            self._run_main(tournaments_file, excluded_file, done_events_file, ["--yes"])

            with open(tournaments_file, encoding="utf-8") as f:
                remaining = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(remaining, [])

    def test_phase_level_exclusion_is_not_treated_as_whole_event_exclusion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file, excluded_file, done_events_file, event_dir = self._setup(tmpdir, phase_level=True)

            self._run_main(tournaments_file, excluded_file, done_events_file, ["--yes"])

            self.assertTrue(os.path.isdir(event_dir))
            with open(tournaments_file, encoding="utf-8") as f:
                remaining = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(remaining), 1)


if __name__ == "__main__":
    unittest.main()
