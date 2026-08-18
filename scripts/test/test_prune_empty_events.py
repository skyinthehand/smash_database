import json
import tempfile
import unittest
from pathlib import Path

from scripts.fix import prune_empty_events as pee
from scripts.utils import read_tournaments_jsonl


def make_event_dir(root, name, standings_count=0, matches_count=0) -> Path:
    event_dir = Path(root) / name
    event_dir.mkdir(parents=True, exist_ok=True)
    (event_dir / "standings.json").write_text(
        json.dumps({"data": [{"placement": i} for i in range(standings_count)]}), encoding="utf-8"
    )
    (event_dir / "matches.json").write_text(
        json.dumps({"data": [{"winner_id": i} for i in range(matches_count)]}), encoding="utf-8"
    )
    return event_dir


def write_tournament_record(path, tournament_id, name, event_id, event_dir) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "tournament_id": tournament_id,
                "name": name,
                "events": [{"event_id": event_id, "event_name": name, "path": str(event_dir)}],
            },
            f,
        )
        f.write("\n")


class PruneEmptyEventsTests(unittest.TestCase):
    # -- US2: count_data_entries / is_empty_event ------------------------------

    def test_count_data_entries_zero_for_missing_or_empty_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing.json"
            self.assertEqual(pee.count_data_entries(missing), 0)

            empty = Path(tmpdir) / "empty.json"
            empty.write_text(json.dumps({"data": []}), encoding="utf-8")
            self.assertEqual(pee.count_data_entries(empty), 0)

            populated = Path(tmpdir) / "populated.json"
            populated.write_text(json.dumps({"data": [{"a": 1}, {"a": 2}]}), encoding="utf-8")
            self.assertEqual(pee.count_data_entries(populated), 2)

    def test_is_empty_event_true_when_both_standings_and_matches_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "empty_event")
            self.assertTrue(pee.is_empty_event(event_dir))

    def test_is_empty_event_false_when_either_has_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            standings_only = make_event_dir(tmpdir, "s", standings_count=3, matches_count=0)
            matches_only = make_event_dir(tmpdir, "m", standings_count=0, matches_count=3)
            self.assertFalse(pee.is_empty_event(standings_only))
            self.assertFalse(pee.is_empty_event(matches_only))

    # -- US2: find_empty_event_dirs -------------------------------------------

    def test_find_empty_event_dirs_returns_only_empty_ones(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = make_event_dir(tmpdir, "Japan/t1/empty")
            real_dir = make_event_dir(tmpdir, "Japan/t2/real", standings_count=8, matches_count=10)

            found = pee.find_empty_event_dirs(Path(tmpdir))

            self.assertIn(empty_dir, found)
            self.assertNotIn(real_dir, found)

    # -- US2: prune_empty_events ------------------------------------------------

    def test_prune_empty_events_dry_run_does_not_modify_filesystem_or_tournaments_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = make_event_dir(tmpdir, "Japan/t1/empty")
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournament_record(tournament_file_path, 1, "T", 10, empty_dir)
            content_before = Path(tournament_file_path).read_text(encoding="utf-8")

            summary = pee.prune_empty_events(Path(tmpdir), tournament_file_path, apply=False)

            self.assertTrue(empty_dir.is_dir())
            self.assertEqual(Path(tournament_file_path).read_text(encoding="utf-8"), content_before)
            self.assertEqual(summary["found"], 1)
            self.assertEqual(summary["deleted"], 0)

    def test_prune_empty_events_apply_deletes_dirs_and_updates_tournaments_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = make_event_dir(tmpdir, "Japan/t1/empty")
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournament_record(tournament_file_path, 1, "T", 10, empty_dir)

            summary = pee.prune_empty_events(Path(tmpdir), tournament_file_path, apply=True)

            self.assertFalse(empty_dir.exists())
            self.assertEqual(summary["deleted"], 1)
            updated = read_tournaments_jsonl(tournament_file_path)
            self.assertEqual(updated[1]["events"], [])

    def test_prune_empty_events_apply_leaves_non_empty_directories_and_their_records_untouched(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            real_dir = make_event_dir(tmpdir, "Japan/t2/real", standings_count=8, matches_count=10)
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournament_record(tournament_file_path, 2, "T2", 20, real_dir)

            summary = pee.prune_empty_events(Path(tmpdir), tournament_file_path, apply=True)

            self.assertTrue(real_dir.is_dir())
            self.assertEqual(summary["deleted"], 0)
            updated = read_tournaments_jsonl(tournament_file_path)
            self.assertEqual(len(updated[2]["events"]), 1)


if __name__ == "__main__":
    unittest.main()
