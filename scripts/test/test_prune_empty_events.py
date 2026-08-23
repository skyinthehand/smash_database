import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.fix import prune_empty_events as pee
from scripts.utils import FetchError, NoEventsForGameError, read_tournaments_jsonl


def make_event_dir(root, name, standings_count=0, matches_count=0, event_id=None) -> Path:
    event_dir = Path(root) / name
    event_dir.mkdir(parents=True, exist_ok=True)
    (event_dir / "standings.json").write_text(
        json.dumps({"data": [{"placement": i} for i in range(standings_count)]}), encoding="utf-8"
    )
    (event_dir / "matches.json").write_text(
        json.dumps({"data": [{"winner_id": i} for i in range(matches_count)]}), encoding="utf-8"
    )
    if event_id is not None:
        (event_dir / "attr.json").write_text(json.dumps({"event_id": event_id}), encoding="utf-8")
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


def write_real_data(event_dir, *_args, **_kwargs) -> bool:
    """backfill_one_event() の代わりに使う。再取得の結果、実データが見つかったことを模す。"""
    Path(event_dir, "standings.json").write_text(json.dumps({"data": [{"placement": 1}]}), encoding="utf-8")
    Path(event_dir, "matches.json").write_text(json.dumps({"data": [{"winner_id": 1}]}), encoding="utf-8")
    return True


def write_still_empty(event_dir, *_args, **_kwargs) -> bool:
    """backfill_one_event() の代わりに使う。再取得しても空のままだったことを模す。"""
    return True


class PruneEmptyEventsTests(unittest.TestCase):
    # -- ローカル判定(一次選別) -------------------------------------------

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

    def test_find_empty_event_dirs_returns_only_empty_ones(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = make_event_dir(tmpdir, "Japan/t1/empty")
            real_dir = make_event_dir(tmpdir, "Japan/t2/real", standings_count=8, matches_count=10)

            found = pee.find_empty_event_dirs(Path(tmpdir))

            self.assertIn(empty_dir, found)
            self.assertNotIn(real_dir, found)

    # -- event_id / tournament_id の特定 --------------------------------------

    def test_resolve_event_id_from_attr_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "e", event_id=42)
            self.assertEqual(pee.resolve_event_id(event_dir, {}), 42)

    def test_resolve_event_id_falls_back_to_tournaments_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "e")  # attr.json 無し
            tournaments = {1: {"tournament_id": 1, "events": [{"event_id": 99, "path": str(event_dir)}]}}
            self.assertEqual(pee.resolve_event_id(event_dir, tournaments), 99)

    def test_resolve_event_id_returns_none_when_unresolvable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "e")
            self.assertIsNone(pee.resolve_event_id(event_dir, {}))

    def test_resolve_tournament_id_matches_by_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "e", event_id=42)
            tournaments = {811466: {"tournament_id": 811466, "events": [{"event_id": 42, "path": str(event_dir)}]}}
            self.assertEqual(pee.resolve_tournament_id(42, event_dir, tournaments), 811466)

    # -- 兄弟イベントの確認 -----------------------------------------------------

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament")
    def test_has_unrecorded_sibling_event_true_when_new_event_found(self, mock_fetch):
        mock_fetch.return_value = [(1533881, "Singles", False, "COMPLETED", 1)]
        tournaments = {811466: {"tournament_id": 811466, "events": [{"event_id": 1423946, "path": "x"}]}}
        self.assertTrue(pee.has_unrecorded_sibling_event(811466, "1386", tournaments))

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament")
    def test_has_unrecorded_sibling_event_false_when_no_other_events(self, mock_fetch):
        mock_fetch.return_value = [(1423946, "Singles", False, "COMPLETED", 1)]
        tournaments = {811466: {"tournament_id": 811466, "events": [{"event_id": 1423946, "path": "x"}]}}
        self.assertFalse(pee.has_unrecorded_sibling_event(811466, "1386", tournaments))

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament")
    def test_has_unrecorded_sibling_event_none_on_fetch_error(self, mock_fetch):
        mock_fetch.side_effect = FetchError("network error")
        tournaments = {811466: {"tournament_id": 811466, "events": []}}
        self.assertIsNone(pee.has_unrecorded_sibling_event(811466, "1386", tournaments))

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament")
    def test_has_unrecorded_sibling_event_false_when_no_events_for_game(self, mock_fetch):
        # NoEventsForGameError(GraphQLのerrorsを伴わずeventsがnull)は「確認できた上で
        # 0件」を意味するため、通常のFetchError(確認不能)とは区別してFalseを返す。
        mock_fetch.side_effect = NoEventsForGameError("events is null in response, no GraphQL errors present")
        tournaments = {811466: {"tournament_id": 811466, "events": []}}
        self.assertFalse(pee.has_unrecorded_sibling_event(811466, "1386", tournaments))

    # -- reconcile_empty_event(削除可否の総合判定) --------------------------------

    @patch("scripts.fix.prune_empty_events.backfill_one_event", side_effect=write_real_data)
    def test_reconcile_heals_when_refetch_finds_real_data(self, _mock_backfill):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "e", event_id=1533881)
            tournaments = {867504: {"tournament_id": 867504, "events": [{"event_id": 1533881, "path": str(event_dir)}]}}

            outcome = pee.reconcile_empty_event(event_dir, tournaments, {}, f"{tmpdir}/users.jsonl", "1386")

            self.assertEqual(outcome, "healed")
            self.assertTrue(event_dir.is_dir())
            self.assertFalse(pee.is_empty_event(event_dir))

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament", return_value=[])
    @patch("scripts.fix.prune_empty_events.backfill_one_event", side_effect=write_still_empty)
    def test_reconcile_deletes_when_still_empty_and_no_sibling(self, _mock_backfill, _mock_fetch):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "e", event_id=1423946)
            tournaments = {811466: {"tournament_id": 811466, "events": [{"event_id": 1423946, "path": str(event_dir)}]}}

            outcome = pee.reconcile_empty_event(event_dir, tournaments, {}, f"{tmpdir}/users.jsonl", "1386")

            self.assertEqual(outcome, "deleted")
            self.assertFalse(event_dir.exists())

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament")
    @patch("scripts.fix.prune_empty_events.backfill_one_event", side_effect=write_still_empty)
    def test_reconcile_keeps_when_sibling_event_exists(self, _mock_backfill, mock_fetch):
        mock_fetch.return_value = [(1423946, "Singles", False, "COMPLETED", 1), (1533881, "Singles", False, "COMPLETED", 1)]
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "e", event_id=1423946)
            tournaments = {811466: {"tournament_id": 811466, "events": [{"event_id": 1423946, "path": str(event_dir)}]}}

            outcome = pee.reconcile_empty_event(event_dir, tournaments, {}, f"{tmpdir}/users.jsonl", "1386")

            self.assertEqual(outcome, "kept")
            self.assertTrue(event_dir.is_dir())

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament")
    @patch("scripts.fix.prune_empty_events.backfill_one_event", side_effect=write_still_empty)
    def test_reconcile_keeps_when_sibling_check_is_inconclusive(self, _mock_backfill, mock_fetch):
        mock_fetch.side_effect = FetchError("events is null in response")
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "e", event_id=1423946)
            tournaments = {811466: {"tournament_id": 811466, "events": [{"event_id": 1423946, "path": str(event_dir)}]}}

            outcome = pee.reconcile_empty_event(event_dir, tournaments, {}, f"{tmpdir}/users.jsonl", "1386")

            self.assertEqual(outcome, "kept")
            self.assertTrue(event_dir.is_dir())

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament")
    @patch("scripts.fix.prune_empty_events.backfill_one_event", side_effect=write_still_empty)
    def test_reconcile_deletes_when_tournament_confirmed_to_have_no_events_for_game(self, _mock_backfill, mock_fetch):
        # 第7回チバスマ交流会(tournament_id=811466)を模したケース: 兄弟イベント確認が
        # NoEventsForGameError(GraphQLのerrorsを伴わずeventsがnull)を返す場合、
        # 「確認できた上で0件」として削除対象になる。
        mock_fetch.side_effect = NoEventsForGameError("events is null in response, no GraphQL errors present")
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "e", event_id=1423946)
            tournaments = {811466: {"tournament_id": 811466, "events": [{"event_id": 1423946, "path": str(event_dir)}]}}

            outcome = pee.reconcile_empty_event(event_dir, tournaments, {}, f"{tmpdir}/users.jsonl", "1386")

            self.assertEqual(outcome, "deleted")
            self.assertFalse(event_dir.exists())

    def test_reconcile_keeps_when_event_id_unresolvable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = make_event_dir(tmpdir, "e")  # attr.json 無し、tournaments にも記録無し
            outcome = pee.reconcile_empty_event(event_dir, {}, {}, f"{tmpdir}/users.jsonl", "1386")

            self.assertEqual(outcome, "kept")
            self.assertTrue(event_dir.is_dir())

    # -- prune_empty_events(全体のオーケストレーション) ---------------------------

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament")
    def test_prune_empty_events_dry_run_makes_no_api_calls_or_changes(self, mock_fetch):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = make_event_dir(tmpdir, "Japan/t1/empty", event_id=1423946)
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournament_record(tournament_file_path, 811466, "T", 1423946, empty_dir)
            content_before = Path(tournament_file_path).read_text(encoding="utf-8")

            summary = pee.prune_empty_events(
                Path(tmpdir), tournament_file_path, f"{tmpdir}/users.jsonl", "1386", apply=False
            )

            self.assertEqual(summary["found"], 1)
            self.assertEqual(summary["deleted"], 0)
            self.assertTrue(empty_dir.is_dir())
            self.assertEqual(Path(tournament_file_path).read_text(encoding="utf-8"), content_before)
        mock_fetch.assert_not_called()

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament", return_value=[])
    @patch("scripts.fix.prune_empty_events.backfill_one_event", side_effect=write_still_empty)
    def test_prune_empty_events_apply_deletes_confirmed_empty_and_updates_tournaments_jsonl(
        self, _mock_backfill, _mock_fetch
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = make_event_dir(tmpdir, "Japan/t1/empty", event_id=1423946)
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournament_record(tournament_file_path, 811466, "T", 1423946, empty_dir)

            summary = pee.prune_empty_events(
                Path(tmpdir), tournament_file_path, f"{tmpdir}/users.jsonl", "1386", apply=True
            )

            self.assertEqual(summary["deleted"], 1)
            self.assertFalse(empty_dir.exists())
            updated = read_tournaments_jsonl(tournament_file_path)
            self.assertEqual(updated[811466]["events"], [])

    @patch("scripts.fix.prune_empty_events.fetch_event_ids_from_tournament")
    @patch("scripts.fix.prune_empty_events.backfill_one_event", side_effect=write_still_empty)
    def test_prune_empty_events_apply_does_not_delete_when_sibling_event_found(self, _mock_backfill, mock_fetch):
        mock_fetch.return_value = [(1423946, "Singles", False, "COMPLETED", 1), (1533881, "Singles", False, "COMPLETED", 1)]
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = make_event_dir(tmpdir, "Japan/t1/empty", event_id=1423946)
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournament_record(tournament_file_path, 811466, "T", 1423946, empty_dir)

            summary = pee.prune_empty_events(
                Path(tmpdir), tournament_file_path, f"{tmpdir}/users.jsonl", "1386", apply=True
            )

            self.assertEqual(summary["deleted"], 0)
            self.assertEqual(summary["kept"], 1)
            self.assertTrue(empty_dir.is_dir())
            updated = read_tournaments_jsonl(tournament_file_path)
            self.assertEqual(len(updated[811466]["events"]), 1)

    @patch("scripts.fix.prune_empty_events.backfill_one_event", side_effect=write_real_data)
    def test_prune_empty_events_apply_heals_stale_empty_directory_with_real_data(self, _mock_backfill):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = make_event_dir(tmpdir, "Japan/t1/stale", event_id=1533881)
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournament_record(tournament_file_path, 867504, "T", 1533881, empty_dir)

            summary = pee.prune_empty_events(
                Path(tmpdir), tournament_file_path, f"{tmpdir}/users.jsonl", "1386", apply=True
            )

            self.assertEqual(summary["healed"], 1)
            self.assertEqual(summary["deleted"], 0)
            self.assertTrue(empty_dir.is_dir())
            self.assertFalse(pee.is_empty_event(empty_dir))
            updated = read_tournaments_jsonl(tournament_file_path)
            self.assertEqual(len(updated[867504]["events"]), 1)

    def test_prune_empty_events_apply_leaves_non_empty_directories_and_their_records_untouched(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            real_dir = make_event_dir(tmpdir, "Japan/t2/real", standings_count=8, matches_count=10, event_id=20)
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournament_record(tournament_file_path, 2, "T2", 20, real_dir)

            summary = pee.prune_empty_events(
                Path(tmpdir), tournament_file_path, f"{tmpdir}/users.jsonl", "1386", apply=True
            )

            self.assertTrue(real_dir.is_dir())
            self.assertEqual(summary["deleted"], 0)
            self.assertEqual(summary["healed"], 0)
            updated = read_tournaments_jsonl(tournament_file_path)
            self.assertEqual(len(updated[2]["events"]), 1)


if __name__ == "__main__":
    unittest.main()
