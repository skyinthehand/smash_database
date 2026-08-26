import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts.fetch import backfill_schema_version as bsv
from scripts.utils import EVENT_DATA_VERSION


def make_event_dir(root: Path, name: str, event_data_version=None) -> Path:
    event_dir = root / name
    event_dir.mkdir(parents=True, exist_ok=True)
    attr = {"event_id": abs(hash(name)) % 100000, "event_name": name}
    if event_data_version is not None:
        attr["event_data_version"] = event_data_version
    (event_dir / "attr.json").write_text(json.dumps(attr), encoding="utf-8")
    return event_dir


def make_partial_event_dir(root: Path, name: str) -> Path:
    """attr.json を持たない(standings.json のみの)イベントディレクトリを作る。"""
    event_dir = root / name
    event_dir.mkdir(parents=True, exist_ok=True)
    (event_dir / "standings.json").write_text(json.dumps({"data": []}), encoding="utf-8")
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
        self.assertEqual(
            summary, {"processed": 0, "skipped": 3, "wrapped_around": False, "unresolved": 0}
        )

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
             patch.object(bsv, "download_all_set", return_value=False), \
             patch.object(bsv, "extend_user_info"), \
             patch.object(bsv, "write_event_attributes") as mocked_write:
            result = bsv.backfill_one_event(event_dir, {}, self.users_file_path)

        self.assertTrue(result)
        mocked_write.assert_called_once()
        self.assertEqual(mocked_write.call_args.kwargs.get("end_at"), 1710086400)

    # -- US2: event_data_version=2 の既存イベントがバックフィルで end_at を獲得する ---

    def test_outdated_event_gains_end_at_and_reaches_current_version(self):
        event_dir = make_event_dir(self.events_root, "legacy_event", event_data_version=2)
        attr_before = json.loads((event_dir / "attr.json").read_text(encoding="utf-8"))
        event_id = attr_before["event_id"]

        event = {"name": "Event", "startAt": 1710001000, "isOnline": True}
        tournament = {"name": "Tournament", "url": "https://example.com", "endAt": 1710086400}

        with patch.object(bsv, "fetch_event_details", return_value=(event, tournament)), \
             patch.object(bsv, "download_standings", return_value=([], [], {})), \
             patch.object(bsv, "download_seeds"), \
             patch.object(bsv, "download_all_set", return_value=False), \
             patch.object(bsv, "extend_user_info"):
            summary = bsv.run_backfill(
                self.events_root, self.users_file_path, self.cursor_path, max_events=0
            )

        self.assertEqual(summary["processed"], 1)
        attr_after = json.loads((event_dir / "attr.json").read_text(encoding="utf-8"))
        self.assertEqual(attr_after["end_at"], 1710086400)
        self.assertEqual(attr_after["event_data_version"], EVENT_DATA_VERSION)

    def test_backfill_one_event_does_not_write_attr_json_while_sets_still_incomplete(self):
        # FR-010/FR-012: download_all_set() が「まだプレースホルダーが残っている」
        # (=一括取得が失敗し逐次取得モードに入ったまま完了していない)ことを示す True を
        # 返した場合、backfill_one_event は attr.json を書いてはならない。書いてしまうと
        # event_data_version が最新になり、このイベントが以後の巡回スキャン対象から
        # 外れて二度と完了できなくなる(以前に発見した回帰)。
        event_dir = make_partial_event_dir(self.events_root, "Japan/tournament_large/event_large")

        tournaments = {
            1: {
                "tournament_id": 1,
                "events": [{"event_id": 999, "event_name": "event_large", "path": str(event_dir)}],
            }
        }
        event = {"name": "Event", "startAt": 1710001000, "isOnline": True}
        tournament = {"name": "Tournament", "url": "https://example.com", "endAt": 1710086400}

        with patch.object(bsv, "fetch_event_details", return_value=(event, tournament)), \
             patch.object(bsv, "download_standings", return_value=([], [], {})), \
             patch.object(bsv, "download_seeds"), \
             patch.object(bsv, "download_all_set", return_value=True), \
             patch.object(bsv, "extend_user_info"), \
             patch.object(bsv, "write_event_attributes") as mocked_write:
            result = bsv.backfill_one_event(event_dir, {}, self.users_file_path, tournaments=tournaments)

        self.assertTrue(result)
        mocked_write.assert_not_called()
        self.assertFalse((event_dir / "attr.json").exists())

    def test_event_left_incomplete_by_backfill_remains_eligible_next_cycle(self):
        # 上のテストで書かれなかった attr.json の不在により、read_event_data_version() は
        # 0 を返し続け、このイベントは次回の巡回でも再度対象になる。
        event_dir = make_partial_event_dir(self.events_root, "Japan/tournament_large/event_large")

        self.assertEqual(bsv.read_event_data_version(event_dir), 0)
        self.assertLess(bsv.read_event_data_version(event_dir), EVENT_DATA_VERSION)

    # -- US2: attr.json が欠落したディレクトリも発見・補完される ----------------

    def test_discovers_directories_missing_attr_json_via_standings(self):
        event_dir = make_partial_event_dir(self.events_root, "Japan/tournament_x/event_x")

        order = [str(p) for p in bsv.iter_event_dirs(self.events_root)]

        self.assertIn(str(event_dir), order)

    def test_backfill_one_event_recovers_event_id_from_tournaments_jsonl_when_attr_json_missing(self):
        event_dir = make_partial_event_dir(self.events_root, "Japan/tournament_y/event_y")

        tournaments = {
            1: {
                "tournament_id": 1,
                "events": [{"event_id": 555, "event_name": "event_y", "path": str(event_dir)}],
            }
        }
        event = {"name": "Event", "startAt": 1710001000, "isOnline": True}
        tournament = {"name": "Tournament", "url": "https://example.com", "endAt": 1710086400}

        with patch.object(bsv, "fetch_event_details", return_value=(event, tournament)) as mocked_fetch, \
             patch.object(bsv, "download_standings", return_value=([], [], {})), \
             patch.object(bsv, "download_seeds"), \
             patch.object(bsv, "download_all_set", return_value=False), \
             patch.object(bsv, "extend_user_info"), \
             patch.object(bsv, "write_event_attributes") as mocked_write:
            result = bsv.backfill_one_event(event_dir, {}, self.users_file_path, tournaments=tournaments)

        self.assertTrue(result)
        mocked_fetch.assert_called_once_with(555)
        mocked_write.assert_called_once()

    def test_backfill_one_event_reports_unresolved_when_event_id_cannot_be_determined(self):
        event_dir = make_partial_event_dir(self.events_root, "Japan/tournament_z/event_z")
        unresolved = []

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = bsv.backfill_one_event(
                event_dir, {}, self.users_file_path, tournaments={}, unresolved=unresolved
            )

        self.assertFalse(result)
        self.assertIn(str(event_dir), unresolved)
        self.assertIn("[UNRESOLVED]", stderr.getvalue())

    def test_run_backfill_counts_unresolved_events_and_continues(self):
        # tournament_file_path を渡さない(=tournaments.jsonl からの復元ができない)場合、
        # attr.json を持たないディレクトリは [UNRESOLVED] として計上され、
        # 他のイベントの処理は継続する。
        make_partial_event_dir(self.events_root, "Japan/tournament_z/event_z")
        make_event_dir(self.events_root, "current", event_data_version=bsv.EVENT_DATA_VERSION)

        summary = bsv.run_backfill(
            self.events_root, self.users_file_path, self.cursor_path, max_events=0
        )

        self.assertEqual(summary["unresolved"], 1)
        self.assertEqual(summary["processed"], 1)
        self.assertEqual(summary["skipped"], 1)

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
