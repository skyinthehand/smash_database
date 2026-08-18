import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.fetch import backfill_tournament_events as bte
from scripts.utils import FetchError, get_date_parts, get_event_directory


def make_tournaments(n: int) -> dict:
    return {i: {"tournament_id": i, "name": f"Tournament {i}", "events": []} for i in range(n)}


def write_tournaments_jsonl(path: str, tournaments: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for tournament in tournaments.values():
            json.dump(tournament, f, ensure_ascii=False)
            f.write("\n")


class BackfillTournamentEventsTests(unittest.TestCase):
    # -- US1: iter_tournament_ids ------------------------------------------

    def test_iter_tournament_ids_includes_tournaments_with_zero_events(self):
        tournaments = {
            1: {"tournament_id": 1, "name": "A", "events": [{"event_id": 10, "event_name": "E", "path": "x"}]},
            2: {"tournament_id": 2, "name": "B", "events": []},
        }

        ids = bte.iter_tournament_ids(tournaments)

        self.assertIn(1, ids)
        self.assertIn(2, ids)

    # -- US1: find_new_event_ids ---------------------------------------------

    @patch("scripts.fetch.backfill_tournament_events.fetch_event_ids_from_tournament")
    def test_find_new_event_ids_returns_only_unrecorded_event_ids(self, mock_fetch):
        mock_fetch.return_value = [(10, "Singles", False), (20, "Doubles", False)]

        new_ids = bte.find_new_event_ids(811466, "1386", recorded_event_ids={10})

        self.assertEqual(new_ids, [20])

    @patch("scripts.fetch.backfill_tournament_events.fetch_event_ids_from_tournament")
    def test_find_new_event_ids_returns_empty_list_on_fetch_error(self, mock_fetch):
        mock_fetch.side_effect = FetchError("events is null in response")

        new_ids = bte.find_new_event_ids(811466, "1386", recorded_event_ids=set())

        self.assertEqual(new_ids, [])

    # -- US1: save_new_event --------------------------------------------------

    @patch("scripts.fetch.backfill_tournament_events.download_all_set")
    @patch("scripts.fetch.backfill_tournament_events.extend_user_info")
    @patch("scripts.fetch.backfill_tournament_events.download_seeds")
    @patch("scripts.fetch.backfill_tournament_events.download_standings")
    @patch("scripts.fetch.backfill_tournament_events.fetch_event_details")
    def test_save_new_event_writes_attr_json_and_updates_tournaments_dict(
        self, mock_fetch_details, mock_standings, _mock_seeds, _mock_extend, _mock_sets
    ):
        mock_fetch_details.return_value = (
            {"name": "Singles", "startAt": 1770422400, "isOnline": False},
            {
                "name": "Test Tournament",
                "url": "https://example.com",
                "endAt": 1770426000,
                "countryCode": "JP",
                "city": "Chiba",
                "lat": None,
                "lng": None,
                "venueName": None,
                "timezone": "Asia/Tokyo",
                "postalCode": None,
                "venueAddress": None,
                "mapsPlaceId": None,
            },
        )
        mock_standings.return_value = ([], [], {})

        with tempfile.TemporaryDirectory() as tmpdir:
            year, month, day = get_date_parts(1770422400)
            expected_dir = get_event_directory(tmpdir, "JP", year, month, day, "Test Tournament", "Singles")
            os.makedirs(expected_dir, exist_ok=True)

            tournaments = {811466: {"tournament_id": 811466, "name": "Test Tournament", "events": []}}
            result = bte.save_new_event(
                811466, "Test Tournament", 1533881, "JP", tmpdir, tournaments, {}, f"{tmpdir}/users.jsonl"
            )

            self.assertTrue(result)
            self.assertEqual(len(tournaments[811466]["events"]), 1)
            self.assertEqual(tournaments[811466]["events"][0]["event_id"], 1533881)
            new_dir = tournaments[811466]["events"][0]["path"]
            self.assertTrue(os.path.isfile(os.path.join(new_dir, "attr.json")))

    @patch("scripts.fetch.backfill_tournament_events.fetch_event_details")
    def test_save_new_event_returns_false_and_does_not_raise_on_fetch_error(self, mock_fetch_details):
        mock_fetch_details.side_effect = FetchError("Event 999 not found.")

        tournaments = {811466: {"tournament_id": 811466, "name": "Test Tournament", "events": []}}
        result = bte.save_new_event(
            811466, "Test Tournament", 999, "JP", "/tmp/does-not-matter", tournaments, {}, "/tmp/users.jsonl"
        )

        self.assertFalse(result)
        self.assertEqual(tournaments[811466]["events"], [])

    # -- US1: run_tournament_event_sync(カーソル・循環スキャン) ------------------

    @patch("scripts.fetch.backfill_tournament_events.find_new_event_ids", return_value=[])
    def test_run_tournament_event_sync_cursor_resumes_from_last_position(self, mock_find):
        tournaments = make_tournaments(3)

        with tempfile.TemporaryDirectory() as tmpdir:
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournaments_jsonl(tournament_file_path, tournaments)
            cursor_path = Path(tmpdir) / "cursor.txt"

            bte.run_tournament_event_sync(
                tournament_file_path, cursor_path, tmpdir, f"{tmpdir}/users.jsonl", "1386", max_tournaments=1
            )
            first_ids = [call.args[0] for call in mock_find.call_args_list]
            mock_find.reset_mock()

            bte.run_tournament_event_sync(
                tournament_file_path, cursor_path, tmpdir, f"{tmpdir}/users.jsonl", "1386", max_tournaments=1
            )
            second_ids = [call.args[0] for call in mock_find.call_args_list]

        self.assertNotEqual(first_ids, second_ids)

    @patch("scripts.fetch.backfill_tournament_events.find_new_event_ids", return_value=[])
    def test_run_tournament_event_sync_wraps_around_and_still_checks_zero_event_tournament(self, mock_find):
        # done.csv には一切依存しない(FR-006): done_tournaments 相当の概念自体が
        # run_tournament_event_sync のシグネチャに存在しないことも、この設計で保証される。
        tournaments = make_tournaments(2)
        tournaments[1]["events"] = []  # 記録イベント数0件のトーナメントも対象に含まれること

        with tempfile.TemporaryDirectory() as tmpdir:
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournaments_jsonl(tournament_file_path, tournaments)
            cursor_path = Path(tmpdir) / "cursor.txt"

            checked_ids = set()
            for _ in range(2):
                bte.run_tournament_event_sync(
                    tournament_file_path, cursor_path, tmpdir, f"{tmpdir}/users.jsonl", "1386", max_tournaments=1
                )
                checked_ids.update(call.args[0] for call in mock_find.call_args_list)
                mock_find.reset_mock()

        self.assertEqual(checked_ids, {0, 1})

    @patch("scripts.fetch.backfill_tournament_events.find_new_event_ids", return_value=[])
    def test_run_tournament_event_sync_does_not_rewrite_tournaments_jsonl_when_nothing_found(self, mock_find):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournaments_jsonl(tournament_file_path, make_tournaments(1))
            cursor_path = Path(tmpdir) / "cursor.txt"

            with open(tournament_file_path, encoding="utf-8") as f:
                content_before = f.read()

            bte.run_tournament_event_sync(
                tournament_file_path, cursor_path, tmpdir, f"{tmpdir}/users.jsonl", "1386", max_tournaments=0
            )

            with open(tournament_file_path, encoding="utf-8") as f:
                content_after = f.read()

        self.assertEqual(content_before, content_after)
        self.assertTrue(mock_find.called)

    # -- US1: sync_specific_tournaments(カーソルを使わない直接指定) ----------------

    @patch("scripts.fetch.backfill_tournament_events.find_new_event_ids")
    def test_sync_specific_tournaments_checks_only_requested_ids(self, mock_find):
        mock_find.return_value = []
        tournaments = make_tournaments(5)

        with tempfile.TemporaryDirectory() as tmpdir:
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournaments_jsonl(tournament_file_path, tournaments)

            bte.sync_specific_tournaments(
                [3], tournament_file_path, tmpdir, f"{tmpdir}/users.jsonl", "1386"
            )

        checked_ids = [call.args[0] for call in mock_find.call_args_list]
        self.assertEqual(checked_ids, [3])

    def test_sync_specific_tournaments_skips_unknown_tournament_id_without_raising(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            write_tournaments_jsonl(tournament_file_path, make_tournaments(1))

            summary = bte.sync_specific_tournaments(
                [999], tournament_file_path, tmpdir, f"{tmpdir}/users.jsonl", "1386"
            )

        self.assertEqual(summary, {"tournaments_checked": 0, "new_events_found": 0})


if __name__ == "__main__":
    unittest.main()
