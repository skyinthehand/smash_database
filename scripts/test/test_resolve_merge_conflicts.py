import json
import os
import tempfile
import unittest
from unittest.mock import patch

from scripts import resolve_merge_conflicts as rmc


class ResolveAttrJsonConflictsTests(unittest.TestCase):
    """code-reviewで指摘された、modify/delete競合(片側でattr.jsonが削除された
    場合)にデータが消失するバグの回帰テスト。"""

    def _run(self, path, ours_raw, theirs_raw):
        def fake_git_show(stage, p):
            return ours_raw if stage == 2 else theirs_raw

        with patch.object(rmc, "git_show", side_effect=fake_git_show), \
             patch(
                 "scripts.check_event_conflicts.list_conflicting_event_paths",
                 return_value=[path],
             ):
            return rmc.resolve_attr_json_conflicts()

    def test_skips_when_ours_side_deleted(self):
        """oursで削除されている(git_showが空文字列を返す)場合、theirs側に
        完全なデータがあっても自動マージせず、ファイルを一切変更しない。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "attr.json")
            original_content = '{"placeholder": true}'
            with open(path, "w", encoding="utf-8") as f:
                f.write(original_content)

            theirs = json.dumps(
                {"event_id": 1, "labels": {"a": True}, "timestamp": 100, "fetched_at": 200}
            )
            touched = self._run(path, "", theirs)

            with open(path, encoding="utf-8") as f:
                after = f.read()

        self.assertEqual(touched, [])
        self.assertEqual(after, original_content)

    def test_skips_when_theirs_side_deleted(self):
        """theirsで削除されている場合も同様に自動マージせず、ファイルを
        一切変更しない(修正前は ours の内容だけで dict(ours)={} 相当になり、
        timestamp/fetched_at以外の全フィールドが失われていた)。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "attr.json")
            original_content = '{"placeholder": true}'
            with open(path, "w", encoding="utf-8") as f:
                f.write(original_content)

            ours = json.dumps(
                {"event_id": 1, "labels": {"a": True}, "timestamp": 100, "fetched_at": 200}
            )
            touched = self._run(path, ours, "")

            with open(path, encoding="utf-8") as f:
                after = f.read()

        self.assertEqual(touched, [])
        self.assertEqual(after, original_content)

    def test_merges_normally_when_both_sides_present(self):
        """両側が正常なJSONの場合は従来通りマージされる(回帰確認)。
        timestamp/fetched_atはそれぞれ値が大きい方、他のフィールドはours。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "attr.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("placeholder")

            ours = json.dumps(
                {"event_id": 1, "labels": {"a": True}, "timestamp": 100, "fetched_at": 500}
            )
            theirs = json.dumps(
                {"event_id": 1, "labels": {"b": True}, "timestamp": 300, "fetched_at": 200}
            )
            touched = self._run(path, ours, theirs)

            with open(path, encoding="utf-8") as f:
                merged = json.load(f)

        self.assertEqual(touched, [path])
        self.assertEqual(merged["labels"], {"a": True})
        self.assertEqual(merged["timestamp"], 300)
        self.assertEqual(merged["fetched_at"], 500)

    def test_skips_when_json_malformed(self):
        """JSONとして壊れている場合は従来通りスキップする(回帰確認、
        ours/theirsどちらも非空文字列だがパースできないケース)。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "attr.json")
            original_content = '{"placeholder": true}'
            with open(path, "w", encoding="utf-8") as f:
                f.write(original_content)

            touched = self._run(path, "{not valid json", "{also not valid")

            with open(path, encoding="utf-8") as f:
                after = f.read()

        self.assertEqual(touched, [])
        self.assertEqual(after, original_content)


if __name__ == "__main__":
    unittest.main()
