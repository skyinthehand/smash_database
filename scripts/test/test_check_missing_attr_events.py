import json
import os
import tempfile
import unittest
from unittest.mock import patch

from scripts.fix import check_missing_attr_events as cme


def _write_tournaments_jsonl(path, tournaments):
    with open(path, "w", encoding="utf-8") as f:
        for t in tournaments:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


class FindEventsMissingAttrTests(unittest.TestCase):
    def test_finds_event_without_attr_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = os.path.join(tmpdir, "event")
            os.makedirs(event_dir)
            tournaments = {
                1: {
                    "tournament_id": 1,
                    "name": "T1",
                    "events": [{"event_id": 10, "event_name": "E1", "path": event_dir}],
                }
            }

            missing = cme.find_events_missing_attr(tournaments)

            self.assertEqual([(1, 10, tournaments[1]["events"][0])], missing)

    def test_skips_event_with_attr_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = os.path.join(tmpdir, "event")
            os.makedirs(event_dir)
            with open(os.path.join(event_dir, "attr.json"), "w", encoding="utf-8") as f:
                f.write("{}")
            tournaments = {
                1: {
                    "tournament_id": 1,
                    "name": "T1",
                    "events": [{"event_id": 10, "event_name": "E1", "path": event_dir}],
                }
            }

            self.assertEqual([], cme.find_events_missing_attr(tournaments))


class FetchEventPublicationStatusTests(unittest.TestCase):
    @patch.object(cme, "fetch_data_with_retries")
    def test_gone_when_event_null_without_errors(self, mock_fetch):
        mock_fetch.return_value = {"data": {"event": None}}

        status, detail = cme.fetch_event_publication_status(10)

        self.assertEqual(status, "gone")
        self.assertIsNone(detail)

    @patch.object(cme, "fetch_data_with_retries")
    def test_found_when_event_present(self, mock_fetch):
        event = {"id": 10, "name": "Singles", "tournament": {"name": "T1"}}
        mock_fetch.return_value = {"data": {"event": event}}

        status, detail = cme.fetch_event_publication_status(10)

        self.assertEqual(status, "found")
        self.assertEqual(detail, event)

    @patch.object(cme, "fetch_data_with_retries")
    def test_inconclusive_when_errors_present_even_if_event_null(self, mock_fetch):
        """一時的な内部エラー(page=17の事例)のようなケース: dataはあるが
        errorsも付いている場合は、event=nullでもgoneと断定しない(fail-closed)。"""
        mock_fetch.return_value = {
            "data": {"event": None},
            "errors": [{"message": "An unknown error has occurred"}],
        }

        status, detail = cme.fetch_event_publication_status(10)

        self.assertEqual(status, "inconclusive")

    @patch.object(cme, "fetch_data_with_retries")
    def test_inconclusive_when_data_key_missing(self, mock_fetch):
        mock_fetch.return_value = {"errors": [{"message": "boom"}]}

        status, detail = cme.fetch_event_publication_status(10)

        self.assertEqual(status, "inconclusive")

    @patch.object(cme, "fetch_data_with_retries")
    def test_inconclusive_when_fetch_raises(self, mock_fetch):
        from scripts.utils import FetchError

        mock_fetch.side_effect = FetchError("network error")

        status, detail = cme.fetch_event_publication_status(10)

        self.assertEqual(status, "inconclusive")


class RemoveEventTests(unittest.TestCase):
    def test_removes_only_target_event_keeps_siblings(self):
        tournaments = {
            1: {
                "tournament_id": 1,
                "name": "T1",
                "events": [
                    {"event_id": 10, "event_name": "E1", "path": "p1"},
                    {"event_id": 11, "event_name": "E2", "path": "p2"},
                ],
            }
        }

        cme.remove_event(tournaments, 1, 10)

        self.assertIn(1, tournaments)
        self.assertEqual([e["event_id"] for e in tournaments[1]["events"]], [11])

    def test_removes_whole_tournament_when_events_becomes_empty(self):
        tournaments = {
            1: {
                "tournament_id": 1,
                "name": "T1",
                "events": [{"event_id": 10, "event_name": "E1", "path": "p1"}],
            }
        }

        cme.remove_event(tournaments, 1, 10)

        self.assertNotIn(1, tournaments)


class MainIntegrationTests(unittest.TestCase):
    """main()を通した統合テスト: dry-runでは書き換えず、--yesではgoneのみ削除する。"""

    def _run_main(self, tmpdir, extra_args, event_statuses):
        tournaments_file = os.path.join(tmpdir, "tournaments.jsonl")
        done_events_file = os.path.join(tmpdir, "done_events.csv")

        event_dirs = {}
        tournaments = []
        for tournament_id, event_id, has_attr in event_statuses:
            event_dir = os.path.join(tmpdir, f"event_{event_id}")
            os.makedirs(event_dir, exist_ok=True)
            if has_attr:
                with open(os.path.join(event_dir, "attr.json"), "w", encoding="utf-8") as f:
                    f.write("{}")
            event_dirs[event_id] = event_dir
            tournaments.append(
                {
                    "tournament_id": tournament_id,
                    "name": f"T{tournament_id}",
                    "events": [{"event_id": event_id, "event_name": "E", "path": event_dir}],
                }
            )
        _write_tournaments_jsonl(tournaments_file, tournaments)
        open(done_events_file, "w").close()

        argv = [
            "check_missing_attr_events.py",
            "--token", "dummy",
            "--tournaments-file", tournaments_file,
            "--done-events-file", done_events_file,
            *extra_args,
        ]
        with patch("sys.argv", argv):
            cme.main()

        with open(tournaments_file, encoding="utf-8") as f:
            remaining_ids = {json.loads(line)["tournament_id"] for line in f if line.strip()}
        return remaining_ids

    @patch.object(cme, "fetch_data_with_retries")
    def test_dry_run_does_not_modify_tournaments_jsonl(self, mock_fetch):
        mock_fetch.return_value = {"data": {"event": None}}

        with tempfile.TemporaryDirectory() as tmpdir:
            remaining_ids = self._run_main(
                tmpdir, [], [(1, 10, False)],
            )

        self.assertEqual(remaining_ids, {1})

    @patch.object(cme, "fetch_data_with_retries")
    def test_yes_removes_only_gone_events(self, mock_fetch):
        def fake_fetch(query, variables):
            event_id = variables["eventId"]
            if event_id == 10:
                return {"data": {"event": None}}  # gone
            return {"data": {"event": {"id": event_id, "name": "still here", "tournament": {}}}}  # found

        mock_fetch.side_effect = fake_fetch

        with tempfile.TemporaryDirectory() as tmpdir:
            remaining_ids = self._run_main(
                tmpdir,
                ["--yes"],
                [(1, 10, False), (2, 11, False)],
            )

        self.assertEqual(remaining_ids, {2})

    @patch.object(cme, "fetch_data_with_retries")
    def test_yes_does_not_touch_events_with_attr_json(self, mock_fetch):
        with tempfile.TemporaryDirectory() as tmpdir:
            remaining_ids = self._run_main(
                tmpdir,
                ["--yes"],
                [(1, 10, True)],
            )

        mock_fetch.assert_not_called()
        self.assertEqual(remaining_ids, {1})


if __name__ == "__main__":
    unittest.main()
