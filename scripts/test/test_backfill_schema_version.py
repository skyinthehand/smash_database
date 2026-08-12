import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.fetch import backfill_schema_version as bsv


def make_event_dir(root: Path, name: str, event_data_version=None) -> Path:
    event_dir = root / name
    event_dir.mkdir(parents=True, exist_ok=True)
    attr = {"event_id": abs(hash(name)) % 100000, "event_name": name}
    if event_data_version is not None:
        attr["event_data_version"] = event_data_version
    (event_dir / "attr.json").write_text(json.dumps(attr), encoding="utf-8")
    return event_dir


class BackfillSchemaVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.events_root = Path(self.tmpdir.name) / "events"
        self.events_root.mkdir()
        self.cursor_path = Path(self.tmpdir.name) / "cursor.txt"
        self.users_file_path = str(Path(self.tmpdir.name) / "users.jsonl")

    # -- 日本の大会を優先してスキャンする ---------------------------------

    def test_japan_region_events_are_scanned_before_other_regions(self):
        make_event_dir(self.events_root, "Europe/tournament_a/event_a", event_data_version=0)
        make_event_dir(self.events_root, "Japan/tournament_b/event_b", event_data_version=0)
        make_event_dir(self.events_root, "North_America/tournament_c/event_c", event_data_version=0)

        order = [str(p) for p in bsv.iter_event_dirs(self.events_root)]
        japan_index = next(i for i, p in enumerate(order) if "/Japan/" in p)
        europe_index = next(i for i, p in enumerate(order) if "/Europe/" in p)
        north_america_index = next(i for i, p in enumerate(order) if "/North_America/" in p)

        self.assertLess(japan_index, europe_index)
        self.assertLess(japan_index, north_america_index)

    # -- US1: 対象検出 -------------------------------------------------

    def test_detects_outdated_and_missing_version_events(self):
        make_event_dir(self.events_root, "current", event_data_version=bsv.EVENT_DATA_VERSION)
        make_event_dir(self.events_root, "outdated", event_data_version=0)
        make_event_dir(self.events_root, "missing")  # event_data_version フィールド自体が無い

        with patch.object(bsv, "backfill_one_event", return_value=True) as mocked:
            summary = bsv.run_backfill(
                self.events_root, self.users_file_path, self.cursor_path, max_events=0
            )

        processed_dirs = {str(call.args[0]) for call in mocked.call_args_list}
        self.assertEqual(mocked.call_count, 2)
        self.assertIn(str(self.events_root / "outdated"), processed_dirs)
        self.assertIn(str(self.events_root / "missing"), processed_dirs)
        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["skipped"], 1)

    # -- US1: カーソルの永続化と再開 -------------------------------------

    def test_cursor_resumes_from_last_position(self):
        for i in range(3):
            make_event_dir(self.events_root, f"event_{i}", event_data_version=0)

        with patch.object(bsv, "backfill_one_event", return_value=True) as mocked:
            summary1 = bsv.run_backfill(
                self.events_root, self.users_file_path, self.cursor_path, max_events=1
            )
        first_processed = [str(call.args[0]) for call in mocked.call_args_list]
        self.assertEqual(summary1["processed"], 1)

        with patch.object(bsv, "backfill_one_event", return_value=True) as mocked2:
            summary2 = bsv.run_backfill(
                self.events_root, self.users_file_path, self.cursor_path, max_events=1
            )
        second_processed = [str(call.args[0]) for call in mocked2.call_args_list]
        self.assertEqual(summary2["processed"], 1)

        # 2回の実行で異なるイベントが処理され、重複や取りこぼしがない
        self.assertNotEqual(first_processed, second_processed)

    # -- US1: 最新イベントはAPI呼び出しなしでスキップ -----------------------

    def test_already_current_events_are_skipped_without_fetch(self):
        for i in range(5):
            make_event_dir(self.events_root, f"event_{i}", event_data_version=bsv.EVENT_DATA_VERSION)

        with patch.object(bsv, "backfill_one_event") as mocked:
            summary = bsv.run_backfill(
                self.events_root, self.users_file_path, self.cursor_path, max_events=0
            )

        mocked.assert_not_called()
        self.assertEqual(summary["processed"], 0)
        self.assertEqual(summary["skipped"], 5)

    # -- US1: 対象0件で正常終了、一周したらカーソルが先頭に戻る ----------------

    def test_no_eligible_events_exits_cleanly(self):
        for i in range(3):
            make_event_dir(self.events_root, f"event_{i}", event_data_version=bsv.EVENT_DATA_VERSION)

        with patch.object(bsv, "backfill_one_event") as mocked:
            summary = bsv.run_backfill(
                self.events_root, self.users_file_path, self.cursor_path, max_events=0
            )

        mocked.assert_not_called()
        self.assertEqual(summary, {"processed": 0, "skipped": 3, "wrapped_around": False})

    def test_wraps_around_after_full_cycle(self):
        for i in range(3):
            make_event_dir(self.events_root, f"event_{i}", event_data_version=0)

        with patch.object(bsv, "backfill_one_event", return_value=True):
            # 1件ずつ3回実行すると、3回目でちょうど一周し終える
            bsv.run_backfill(self.events_root, self.users_file_path, self.cursor_path, max_events=1)
            bsv.run_backfill(self.events_root, self.users_file_path, self.cursor_path, max_events=1)
            summary = bsv.run_backfill(
                self.events_root, self.users_file_path, self.cursor_path, max_events=1
            )

        # 4回目は先頭に戻って処理が再開される
        with patch.object(bsv, "backfill_one_event", return_value=True) as mocked:
            summary4 = bsv.run_backfill(
                self.events_root, self.users_file_path, self.cursor_path, max_events=1
            )
        self.assertEqual(summary4["processed"], 1)
        self.assertTrue(mocked.called)

    # -- US2: バージョン定数を上げるだけで対象が再検出される ------------------

    def test_version_bump_makes_current_events_eligible_again(self):
        make_event_dir(self.events_root, "event_a", event_data_version=bsv.EVENT_DATA_VERSION)

        with patch.object(bsv, "backfill_one_event", return_value=True) as mocked_before:
            summary_before = bsv.run_backfill(
                self.events_root, self.users_file_path, self.cursor_path, max_events=0
            )
        mocked_before.assert_not_called()
        self.assertEqual(summary_before["processed"], 0)

        with patch.object(bsv, "EVENT_DATA_VERSION", bsv.EVENT_DATA_VERSION + 1):
            with patch.object(bsv, "backfill_one_event", return_value=True) as mocked_after:
                summary_after = bsv.run_backfill(
                    self.events_root, self.users_file_path, self.cursor_path, max_events=0
                )
        mocked_after.assert_called_once()
        self.assertEqual(summary_after["processed"], 1)

    # -- US1: backfill_one_event が tournament.endAt を end_at として保存する ---

    def test_backfill_one_event_passes_tournament_end_at_to_write_event_attributes(self):
        event_dir = make_event_dir(self.events_root, "event_with_id", event_data_version=0)
        attr = json.loads((event_dir / "attr.json").read_text(encoding="utf-8"))
        event_id = attr["event_id"]

        event = {"name": "Event", "startAt": 1710001000, "isOnline": True}
        tournament = {"name": "Tournament", "url": "https://example.com", "endAt": 1710086400}

        with patch.object(bsv, "fetch_event_details", return_value=(event, tournament)), \
             patch.object(bsv, "download_standings", return_value=([], [], {})), \
             patch.object(bsv, "download_seeds"), \
             patch.object(bsv, "download_all_set"), \
             patch.object(bsv, "extend_user_info"), \
             patch.object(bsv, "write_event_attributes") as mocked_write:
            result = bsv.backfill_one_event(event_dir, {}, self.users_file_path)

        self.assertTrue(result)
        mocked_write.assert_called_once()
        self.assertEqual(mocked_write.call_args.kwargs.get("end_at"), 1710086400)

    # -- US2: event_data_version=2 の既存イベントがバックフィルで end_at を獲得する ---

    def test_outdated_event_gains_end_at_and_reaches_version_3(self):
        event_dir = make_event_dir(self.events_root, "legacy_event", event_data_version=2)
        attr_before = json.loads((event_dir / "attr.json").read_text(encoding="utf-8"))
        event_id = attr_before["event_id"]

        event = {"name": "Event", "startAt": 1710001000, "isOnline": True}
        tournament = {"name": "Tournament", "url": "https://example.com", "endAt": 1710086400}

        with patch.object(bsv, "fetch_event_details", return_value=(event, tournament)), \
             patch.object(bsv, "download_standings", return_value=([], [], {})), \
             patch.object(bsv, "download_seeds"), \
             patch.object(bsv, "download_all_set"), \
             patch.object(bsv, "extend_user_info"):
            summary = bsv.run_backfill(
                self.events_root, self.users_file_path, self.cursor_path, max_events=0
            )

        self.assertEqual(summary["processed"], 1)
        attr_after = json.loads((event_dir / "attr.json").read_text(encoding="utf-8"))
        self.assertEqual(attr_after["end_at"], 1710086400)
        self.assertEqual(attr_after["event_data_version"], 3)

    # -- US3: 独自のHTTP実装を持たない(既存のリトライ基盤のみ経由) -------------

    def test_module_does_not_import_http_libraries_directly(self):
        source = Path(bsv.__file__).read_text(encoding="utf-8")
        for forbidden in ("import requests", "import urllib", "from requests", "from urllib"):
            self.assertNotIn(
                forbidden,
                source,
                msg=f"{forbidden} が見つかりました。API アクセスは scripts.utils 経由に限定してください。",
            )


if __name__ == "__main__":
    unittest.main()
