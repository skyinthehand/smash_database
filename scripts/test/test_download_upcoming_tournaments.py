import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from scripts.fetch import download_upcoming_tournaments as dut


def _tournament_node(tournament_id, name="T", events=None, start_at=None, end_at=None):
    if start_at is None:
        start_at = int((datetime.now() + timedelta(days=7)).timestamp())
    return {
        "id": tournament_id,
        "name": name,
        "startAt": start_at,
        "endAt": end_at,
        "countryCode": "JP",
        "isOnline": False,
        "addrState": "Tokyo",
        "city": "Tokyo",
        "lat": 35.0,
        "lng": 139.0,
        "mapsPlaceId": "abc",
        "postalCode": "100-0001",
        "venueAddress": "addr",
        "venueName": "venue",
        "timezone": "Asia/Tokyo",
        "url": f"https://www.start.gg/tournament/{tournament_id}",
        "events": events if events is not None else [],
    }


def _event_node(event_id, name="Singles", num_entrants=10, state="ACTIVE", type_=1, is_online=False):
    return {
        "id": event_id,
        "name": name,
        "numEntrants": num_entrants,
        "state": state,
        "type": type_,
        "isOnline": is_online,
        "startAt": int((datetime.now() + timedelta(days=7)).timestamp()),
    }


def _read_all(paths):
    result = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            result[path] = f.read()
    return result


def _page_response(tournaments, total_pages=1):
    return {
        "data": {
            "tournaments": {
                "nodes": tournaments,
                "pageInfo": {"totalPages": total_pages},
            }
        }
    }


class FetchAllUpcomingTournamentsTests(unittest.TestCase):
    @patch("scripts.fetch.download_upcoming_tournaments.compute_event_labels", return_value=({}, 1))
    @patch("scripts.fetch.download_upcoming_tournaments.fetch_data_with_retries")
    def test_paginates_and_aggregates_multiple_pages(self, mock_fetch, _mock_labels):
        mock_fetch.side_effect = [
            _page_response([_tournament_node(1)], total_pages=2),
            _page_response([_tournament_node(2)], total_pages=2),
        ]

        with patch("scripts.fetch.download_upcoming_tournaments.get_page_delay", return_value=0):
            records = dut.fetch_all_upcoming_tournaments("1386", "JP")

        self.assertEqual(mock_fetch.call_count, 2)
        self.assertEqual({r["tournament_id"] for r in records}, {1, 2})

    @patch("scripts.fetch.download_upcoming_tournaments.compute_event_labels", return_value=({}, 1))
    @patch("scripts.fetch.download_upcoming_tournaments.fetch_data_with_retries")
    def test_excludes_in_progress_or_started_tournament(self, mock_fetch, _mock_labels):
        """開始日時は過去だが終了日時が未来(進行中)の大会は一覧から除外される
        ことを確認する(spec.md Edge Cases)。afterDateフィルタがstart.gg側で
        期待通り効かず、サーバーが進行中の大会を返してしまった場合でも、
        クライアント側の防御フィルタ(startAt <= after_date)で確実に
        除外されることを確認する。"""
        past_start = int((datetime.now() - timedelta(days=1)).timestamp())
        future_start = int((datetime.now() + timedelta(days=7)).timestamp())
        mock_fetch.return_value = _page_response(
            [
                _tournament_node(1, start_at=future_start),
                _tournament_node(999, start_at=past_start, end_at=int((datetime.now() + timedelta(days=1)).timestamp())),
            ],
            total_pages=1,
        )

        with patch("scripts.fetch.download_upcoming_tournaments.get_page_delay", return_value=0):
            records = dut.fetch_all_upcoming_tournaments("1386", "JP")

        self.assertEqual({r["tournament_id"] for r in records}, {1})


class WriteFullOverwriteTests(unittest.TestCase):
    @patch("scripts.fetch.download_upcoming_tournaments.compute_event_labels", return_value=({}, 1))
    @patch("scripts.fetch.download_upcoming_tournaments.fetch_data_with_retries")
    def test_main_overwrites_existing_file_completely(self, mock_fetch, _mock_labels):
        mock_fetch.return_value = _page_response([_tournament_node(2)], total_pages=1)

        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file = os.path.join(tmpdir, "upcoming_tournaments.jsonl")
            with open(tournaments_file, "w", encoding="utf-8") as f:
                f.write(json.dumps({"tournament_id": 999, "name": "stale"}) + "\n")

            argv = [
                "download_upcoming_tournaments.py",
                "--token", "dummy",
                "--tournaments_file", tournaments_file,
            ]
            with patch("sys.argv", argv), patch(
                "scripts.fetch.download_upcoming_tournaments.get_page_delay", return_value=0
            ):
                dut.main()

            with open(tournaments_file, encoding="utf-8") as f:
                records = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tournament_id"], 2)


class DoesNotTouchExistingDataTests(unittest.TestCase):
    @patch("scripts.fetch.download_upcoming_tournaments.compute_event_labels", return_value=({}, 1))
    @patch("scripts.fetch.download_upcoming_tournaments.fetch_data_with_retries")
    def test_does_not_modify_historical_files_or_create_event_directories(self, mock_fetch, _mock_labels):
        mock_fetch.return_value = _page_response([_tournament_node(1)], total_pages=1)

        with tempfile.TemporaryDirectory() as tmpdir:
            events_root = os.path.join(tmpdir, "events")
            os.makedirs(events_root)
            tournaments_jsonl = os.path.join(tmpdir, "tournaments.jsonl")
            done_csv = os.path.join(tmpdir, "done.csv")
            done_events_csv = os.path.join(tmpdir, "done_events.csv")
            for path, content in (
                (tournaments_jsonl, '{"tournament_id": 1}\n'),
                (done_csv, "1\n"),
                (done_events_csv, "1\n"),
            ):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            before = _read_all((tournaments_jsonl, done_csv, done_events_csv))
            before_dirs = set(os.listdir(events_root))

            upcoming_file = os.path.join(tmpdir, "upcoming_tournaments.jsonl")
            argv = [
                "download_upcoming_tournaments.py",
                "--token", "dummy",
                "--tournaments_file", upcoming_file,
            ]
            with patch("sys.argv", argv), patch(
                "scripts.fetch.download_upcoming_tournaments.get_page_delay", return_value=0
            ):
                dut.main()

            after = _read_all((tournaments_jsonl, done_csv, done_events_csv))
            after_dirs = set(os.listdir(events_root))

        self.assertEqual(before, after)
        self.assertEqual(before_dirs, after_dirs)
        self.assertEqual(before_dirs, set())


class NumEntrantsTests(unittest.TestCase):
    @patch("scripts.fetch.download_upcoming_tournaments.compute_event_labels", return_value=({}, 1))
    def test_uses_num_entrants_from_nested_events_when_present(self, _mock_labels):
        node = _event_node(10, num_entrants=42)

        record = dut.build_event_record(node, "Tournament Name")

        self.assertEqual(record["num_entrants"], 42)

    @patch("scripts.fetch.download_upcoming_tournaments.compute_event_labels", return_value=({}, 1))
    @patch("scripts.fetch.download_upcoming_tournaments.fetch_num_entrants_individually", return_value=99)
    def test_falls_back_to_individual_fetch_when_nested_num_entrants_missing(
        self, mock_fallback, _mock_labels
    ):
        node = _event_node(10, num_entrants=None)

        record = dut.build_event_record(node, "Tournament Name")

        mock_fallback.assert_called_once_with(10)
        self.assertEqual(record["num_entrants"], 99)

    @patch("scripts.fetch.download_upcoming_tournaments.fetch_data_with_retries")
    def test_fetch_num_entrants_individually_returns_value_from_api(self, mock_fetch):
        mock_fetch.return_value = {"data": {"event": {"numEntrants": 7}}}

        self.assertEqual(dut.fetch_num_entrants_individually(10), 7)

    @patch("scripts.fetch.download_upcoming_tournaments.fetch_data_with_retries")
    def test_fetch_num_entrants_individually_returns_none_when_event_missing(self, mock_fetch):
        mock_fetch.return_value = {"data": {"event": None}}

        self.assertIsNone(dut.fetch_num_entrants_individually(10))


class LabelingTests(unittest.TestCase):
    @patch("scripts.fetch.download_upcoming_tournaments.compute_event_labels")
    def test_labels_and_label_version_are_included(self, mock_compute):
        mock_compute.return_value = ({"registration_type": True}, 4)
        node = _event_node(10)

        record = dut.build_event_record(node, "制限あり大会")

        mock_compute.assert_called_once_with(None, "制限あり大会", "Singles", dut.EVENT_DATA_VERSION)
        self.assertEqual(record["labels"], {"registration_type": True})
        self.assertEqual(record["label_version"], 4)

    @patch("scripts.fetch.download_upcoming_tournaments.compute_event_labels")
    def test_label_version_none_when_min_event_data_version_not_met(self, mock_compute):
        mock_compute.return_value = ({}, None)
        node = _event_node(10)

        record = dut.build_event_record(node, "Tournament Name")

        self.assertIsNone(record["label_version"])


if __name__ == "__main__":
    unittest.main()
