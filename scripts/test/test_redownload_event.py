import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.fetch.download import disambiguated_dir
from scripts.fix import redownload_event as re_module
from scripts.utils import get_date_parts, get_event_directory


class RedownloadEventExclusionTests(unittest.TestCase):
    """FR-006/US3: 除外リストに登録されたevent_idはスキップされる。"""

    def test_redownload_event_skips_excluded_event_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_root = Path(tmpdir)

            with patch.object(
                re_module, "load_excluded_event_ids", return_value={999: {"reason": "test"}}
            ), patch.object(
                re_module, "fetch_event_details"
            ) as mocked_fetch:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    result = re_module.redownload_event(999, events_root, {}, str(events_root / "users.jsonl"), apply=True)

            self.assertTrue(result)
            mocked_fetch.assert_not_called()
            self.assertIn("[999] excluded", buf.getvalue())

    def test_redownload_event_skips_excluded_event_id_in_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_root = Path(tmpdir)

            with patch.object(
                re_module, "load_excluded_event_ids", return_value={999: {"reason": "test"}}
            ), patch.object(
                re_module, "fetch_event_details"
            ) as mocked_fetch:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    result = re_module.redownload_event(999, events_root, {}, str(events_root / "users.jsonl"), apply=False)

            self.assertTrue(result)
            mocked_fetch.assert_not_called()
            self.assertIn("[999] excluded", buf.getvalue())
            self.assertNotIn("dry-run", buf.getvalue())

    def test_redownload_event_proceeds_for_non_excluded_event_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_root = Path(tmpdir)

            with patch.object(re_module, "load_excluded_event_ids", return_value={}):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    # apply=False (dry-run) なので、実際のAPI呼び出しは発生しない。
                    result = re_module.redownload_event(999, events_root, {}, str(events_root / "users.jsonl"), apply=False)

            self.assertTrue(result)
            self.assertIn("dry-run", buf.getvalue())


class RedownloadEventCollisionTests(unittest.TestCase):
    """US5/FR-012: 既に別event_idのデータがあるディレクトリと衝突する場合、
    redownload_event.py自身の保存先だけをずらす(参加者数比較は行わない)。"""

    TOURNAMENT_ID = 555
    TIMESTAMP = 1700000000

    def _fake_event_and_tournament(self, event_id):
        event = {
            "id": event_id,
            "name": "Singles",
            "startAt": self.TIMESTAMP,
            "isOnline": False,
            "state": "COMPLETED",
            "type": 1,
        }
        tournament = {
            "id": self.TOURNAMENT_ID,
            "name": "Collide Redownload",
            "countryCode": "JP",
            "city": "Tokyo",
            "lat": None,
            "lng": None,
            "venueName": None,
            "timezone": "Asia/Tokyo",
            "postalCode": None,
            "venueAddress": None,
            "mapsPlaceId": None,
            "url": "https://example.com",
            "startAt": self.TIMESTAMP,
            "endAt": self.TIMESTAMP + 3600,
        }
        return event, tournament

    def _run_redownload(self, events_root, event_id):
        event, tournament = self._fake_event_and_tournament(event_id)
        with patch.object(re_module, "load_excluded_event_ids", return_value={}), \
             patch.object(re_module, "fetch_event_details", return_value=(event, tournament)), \
             patch.object(re_module, "download_standings", return_value=([], [], {})), \
             patch.object(re_module, "download_seeds"), \
             patch.object(re_module, "download_all_set"), \
             patch.object(re_module, "extend_user_info"), \
             patch.object(re_module, "write_event_attributes") as mock_write_attrs:
            result = re_module.redownload_event(
                event_id, events_root, {}, str(events_root / "users.jsonl"), apply=True
            )
        return result, mock_write_attrs

    def test_shifts_own_target_when_path_occupied_by_different_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_root = Path(tmpdir)
            year, month, day = get_date_parts(self.TIMESTAMP)
            naive_dir = Path(
                get_event_directory(str(events_root), "JP", year, month, day, "Collide Redownload", "Singles")
            )
            naive_dir.mkdir(parents=True)
            with (naive_dir / "attr.json").open("w", encoding="utf-8") as f:
                json.dump({"event_id": 999}, f)
            with (naive_dir / "matches.json").open("w", encoding="utf-8") as f:
                json.dump({"data": ["untouched"]}, f)

            result, mock_write_attrs = self._run_redownload(events_root, event_id=42)

            self.assertTrue(result)
            # 既存(別event_id=999)のディレクトリの内容は一切変更されていない。
            self.assertEqual(
                json.loads((naive_dir / "attr.json").read_text(encoding="utf-8"))["event_id"], 999
            )
            self.assertEqual(
                json.loads((naive_dir / "matches.json").read_text(encoding="utf-8"))["data"], ["untouched"]
            )

            expected_shifted_dir = Path(disambiguated_dir(str(naive_dir), self.TOURNAMENT_ID))
            self.assertTrue(expected_shifted_dir.is_dir())
            self.assertNotEqual(expected_shifted_dir, naive_dir)
            called_event_dir = Path(mock_write_attrs.call_args.args[9])
            self.assertEqual(called_event_dir, expected_shifted_dir)

    def test_unaffected_when_no_collision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_root = Path(tmpdir)
            year, month, day = get_date_parts(self.TIMESTAMP)
            naive_dir = Path(
                get_event_directory(str(events_root), "JP", year, month, day, "Collide Redownload", "Singles")
            )

            result, mock_write_attrs = self._run_redownload(events_root, event_id=42)

            self.assertTrue(result)
            called_event_dir = Path(mock_write_attrs.call_args.args[9])
            self.assertEqual(called_event_dir, naive_dir)

    def test_repeated_runs_use_the_same_shifted_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_root = Path(tmpdir)
            year, month, day = get_date_parts(self.TIMESTAMP)
            naive_dir = Path(
                get_event_directory(str(events_root), "JP", year, month, day, "Collide Redownload", "Singles")
            )
            naive_dir.mkdir(parents=True)
            with (naive_dir / "attr.json").open("w", encoding="utf-8") as f:
                json.dump({"event_id": 999}, f)

            _, first_mock = self._run_redownload(events_root, event_id=42)
            first_dir = Path(first_mock.call_args.args[9])

            _, second_mock = self._run_redownload(events_root, event_id=42)
            second_dir = Path(second_mock.call_args.args[9])

            self.assertEqual(first_dir, second_dir)
            # 相手側(event_id=999)は2回とも一切変更されていない。
            self.assertEqual(
                json.loads((naive_dir / "attr.json").read_text(encoding="utf-8"))["event_id"], 999
            )


if __name__ == "__main__":
    unittest.main()
