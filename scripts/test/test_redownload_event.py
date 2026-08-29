import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.fix import redownload_event as re_module


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


if __name__ == "__main__":
    unittest.main()
