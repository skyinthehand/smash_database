import tempfile
import unittest
from pathlib import Path

from scripts.fix.fix_missing_tournaments import DEFAULT_REQUIRED_FILES, clean_tournaments


class CleanTournamentsExclusionTests(unittest.TestCase):
    """FR-006/US3: 除外リストに登録されたevent_idは検証・削除判定の対象にならない。"""

    def test_excluded_event_with_incomplete_files_is_kept(self):
        # 通常であれば必須ファイルが揃っていないため [REMOVE] 対象になるはずのevent_idも、
        # 除外リストに登録されていれば検証自体をスキップし、そのまま残す。
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            tournaments = [
                {
                    "tournament_id": 1,
                    "name": "T1",
                    "events": [
                        {"event_id": 999, "event_name": "Singles", "path": "does/not/exist"},
                    ],
                }
            ]

            cleaned, report_lines = clean_tournaments(
                tournaments, repo_root, DEFAULT_REQUIRED_FILES, verbose=False,
                excluded_event_ids={999},
            )

        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["events"], tournaments[0]["events"])
        self.assertTrue(any("[EXCLUDED]" in line and "event_id=999" in line for line in report_lines))
        self.assertFalse(any("[REMOVE]" in line for line in report_lines))

    def test_non_excluded_event_with_incomplete_files_is_still_removed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            tournaments = [
                {
                    "tournament_id": 1,
                    "name": "T1",
                    "events": [
                        {"event_id": 999, "event_name": "Singles", "path": "does/not/exist"},
                    ],
                }
            ]

            cleaned, report_lines = clean_tournaments(
                tournaments, repo_root, DEFAULT_REQUIRED_FILES, verbose=False,
                excluded_event_ids=set(),
            )

        self.assertEqual(cleaned, [])
        self.assertTrue(any("[REMOVE]" in line and "event_id=999" in line for line in report_lines))


if __name__ == "__main__":
    unittest.main()
