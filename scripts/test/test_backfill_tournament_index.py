import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.fix import backfill_tournament_index as bti


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


class BackfillTournamentIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.events_root = Path(self.tmpdir.name) / "events"
        self.events_root.mkdir()
        self.tournament_file_path = Path(self.tmpdir.name) / "tournaments.jsonl"
        self.tournament_file_path.touch()

    def make_local_event_dir(self, region, year, month, day, tournament_name, event_name) -> Path:
        event_dir = self.events_root / region / year / month / day / tournament_name / event_name
        event_dir.mkdir(parents=True, exist_ok=True)
        return event_dir

    def _tournament(self, tid, name, start_at=1000, end_at=1100, country="JP"):
        return {
            "id": tid,
            "name": name,
            "startAt": start_at,
            "endAt": end_at,
            "countryCode": country,
        }

    # -- 新規登録: ローカルに既にデータがあるイベントのみ追加する ------------------

    def test_adds_missing_event_when_local_directory_exists(self):
        self.make_local_event_dir("Japan", "1970", "01", "01", "新京都DSW#34", "Single_Tournament")

        with patch.object(
            bti, "fetch_latest_tournaments_by_game",
            return_value=([self._tournament(999, "新京都DSW#34")], 1),
        ), patch.object(
            bti, "fetch_event_ids_from_tournament",
            return_value=[(111, "Single Tournament", False, "COMPLETED", "SINGLES")],
        ):
            summary = bti.scan_and_fill(
                "1386", "", str(self.events_root), str(self.tournament_file_path)
            )

        self.assertEqual(summary["events_added"], 1)
        self.assertEqual(summary["tournaments_added"], 1)
        records = read_jsonl(self.tournament_file_path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tournament_id"], 999)
        self.assertEqual(records[0]["events"][0]["event_id"], 111)
        self.assertIn("新京都DSW#34/Single_Tournament", records[0]["events"][0]["path"])

    def test_skips_event_without_local_directory(self):
        # ディレクトリを一切作らない: まだダウンロードしていないイベント扱い。
        with patch.object(
            bti, "fetch_latest_tournaments_by_game",
            return_value=([self._tournament(999, "NeverDownloaded")], 1),
        ), patch.object(
            bti, "fetch_event_ids_from_tournament",
            return_value=[(111, "Singles", False, "COMPLETED", "SINGLES")],
        ):
            summary = bti.scan_and_fill(
                "1386", "", str(self.events_root), str(self.tournament_file_path)
            )

        self.assertEqual(summary["events_added"], 0)
        self.assertEqual(summary["tournaments_added"], 0)
        self.assertEqual(read_jsonl(self.tournament_file_path), [])

    def test_skips_unfinished_tournament(self):
        self.make_local_event_dir("Japan", "1970", "01", "01", "Ongoing", "Singles")

        with patch.object(
            bti, "fetch_latest_tournaments_by_game",
            return_value=([self._tournament(999, "Ongoing", end_at=None)], 1),
        ), patch.object(
            bti, "fetch_event_ids_from_tournament"
        ) as mocked_events:
            summary = bti.scan_and_fill(
                "1386", "", str(self.events_root), str(self.tournament_file_path)
            )

        mocked_events.assert_not_called()
        self.assertEqual(summary["events_added"], 0)

    def test_dry_run_does_not_write(self):
        self.make_local_event_dir("Japan", "1970", "01", "01", "新京都DSW#34", "Single_Tournament")

        with patch.object(
            bti, "fetch_latest_tournaments_by_game",
            return_value=([self._tournament(999, "新京都DSW#34")], 1),
        ), patch.object(
            bti, "fetch_event_ids_from_tournament",
            return_value=[(111, "Single Tournament", False, "COMPLETED", "SINGLES")],
        ):
            summary = bti.scan_and_fill(
                "1386", "", str(self.events_root), str(self.tournament_file_path), dry_run=True
            )

        self.assertEqual(summary["events_added"], 1)
        self.assertEqual(read_jsonl(self.tournament_file_path), [])

    def test_max_pages_stops_scan_early(self):
        # total_pages=5 だが max_pages=2 を指定した場合、3ページ目以降は
        # 問い合わせない(--dry-run での動作確認を短時間で終わらせるため)。
        def fake_fetch(game_id, country_code, limit, page):
            return ([self._tournament(page, f"Tournament{page}")], 5)

        with patch.object(
            bti, "fetch_latest_tournaments_by_game", side_effect=fake_fetch
        ) as mocked_pages, patch.object(
            bti, "fetch_event_ids_from_tournament", return_value=[]
        ):
            summary = bti.scan_and_fill(
                "1386", "", str(self.events_root), str(self.tournament_file_path), max_pages=2
            )

        self.assertEqual(mocked_pages.call_count, 2)
        self.assertEqual(summary["pages"], 2)

    def test_adds_missing_event_to_already_registered_tournament(self):
        self.make_local_event_dir("Japan", "1970", "01", "01", "ExistingTournament", "Doubles")
        existing = {
            "tournament_id": 999,
            "name": "ExistingTournament",
            "events": [{"event_id": 111, "event_name": "Singles", "path": "some/other/path"}],
            "version": "1.0",
        }
        with self.tournament_file_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(existing, ensure_ascii=False) + "\n")

        with patch.object(
            bti, "fetch_latest_tournaments_by_game",
            return_value=([self._tournament(999, "ExistingTournament")], 1),
        ), patch.object(
            bti, "fetch_event_ids_from_tournament",
            return_value=[
                (111, "Singles", False, "COMPLETED", "SINGLES"),
                (222, "Doubles", False, "COMPLETED", "DOUBLES"),
            ],
        ):
            summary = bti.scan_and_fill(
                "1386", "", str(self.events_root), str(self.tournament_file_path)
            )

        self.assertEqual(summary["events_added"], 1)
        self.assertEqual(summary["tournaments_added"], 0)
        records = read_jsonl(self.tournament_file_path)
        self.assertEqual(len(records), 1)
        event_ids = {ev["event_id"] for ev in records[0]["events"]}
        self.assertEqual(event_ids, {111, 222})


if __name__ == "__main__":
    unittest.main()
