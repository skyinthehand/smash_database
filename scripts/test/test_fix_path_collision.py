import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.fix import fix_path_collision as fpc

TIMESTAMP = 1774400000  # get_date_parts(TIMESTAMP) -> 2026-03-25
TOURNAMENT_ID_BY_EVENT_ID = {10: 1, 20: 2, 30: 3}


def _fake_event_and_tournament(event_id, tournament_id, tournament_name="T", event_name="Singles"):
    event = {
        "id": event_id,
        "name": event_name,
        "startAt": TIMESTAMP,
        "isOnline": False,
        "state": "COMPLETED",
        "type": 1,
    }
    tournament = {
        "id": tournament_id,
        "name": tournament_name,
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
        "startAt": TIMESTAMP,
        "endAt": TIMESTAMP + 3600,
    }
    return event, tournament


class FixPathCollisionTests(unittest.TestCase):
    """US4/FR-009〜FR-011: 参加者数はローカルファイルを信頼せずstart.ggへ取得し
    直す(attr.jsonのevent_id/num_entrantsは、matches.jsonの逐次取得が未完了の
    まま中断した場合、実際の内容と食い違い得るため)。"""

    def _write_tournaments(self, path: Path, entries):
        with path.open("w", encoding="utf-8") as f:
            for entry in entries:
                json.dump(entry, f, ensure_ascii=False)
                f.write("\n")

    def _run_main(self, argv_tail):
        argv = ["fix_path_collision.py", "--token", "TEST"] + argv_tail
        buf = io.StringIO()
        err = io.StringIO()
        with patch.object(fpc.sys, "argv", argv), redirect_stdout(buf), redirect_stderr(err):
            exit_code = fpc.main()
        return exit_code, buf.getvalue() + err.getvalue()

    def _setup_tournaments(self, root, dir_a, dir_b, eid_a=10, eid_b=20):
        tournaments_file = root / "tournaments.jsonl"
        tid_a = TOURNAMENT_ID_BY_EVENT_ID[eid_a]
        tid_b = TOURNAMENT_ID_BY_EVENT_ID[eid_b]
        self._write_tournaments(
            tournaments_file,
            [
                {"tournament_id": tid_a, "name": "T", "events": [{"event_id": eid_a, "event_name": "Singles", "path": str(dir_a)}]},
                {"tournament_id": tid_b, "name": "T", "events": [{"event_id": eid_b, "event_name": "Singles", "path": str(dir_b)}]},
            ],
        )
        return tournaments_file

    def _patched(self, standings_by_event_id, fetch_failed_event_ids=(), attrs_mock=None):
        def fake_fetch_event_details(event_id):
            if event_id in fetch_failed_event_ids:
                raise fpc.FetchError(f"Event {event_id} not found.")
            tid = TOURNAMENT_ID_BY_EVENT_ID.get(event_id, event_id)
            return _fake_event_and_tournament(event_id, tid)

        def fake_download_standings(event_id, event_dir, max_pages=None):
            count = standings_by_event_id[event_id]
            return [None] * count, [None] * count, {}

        return patch.multiple(
            fpc,
            fetch_event_details=fake_fetch_event_details,
            download_standings=fake_download_standings,
            download_seeds=lambda *a, **k: None,
            download_all_set=lambda *a, **k: False,
            write_event_attributes=attrs_mock or (lambda *a, **k: None),
        )

    def test_dry_run_probes_participants_without_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_root = root / "events"
            naive_dir = events_root / "Japan" / "2026" / "03" / "25" / "T" / "Singles"
            tournaments_file = self._setup_tournaments(root, naive_dir, naive_dir)

            with self._patched({10: 0, 20: 9}):
                exit_code, output = self._run_main([
                    "--tournaments-file", str(tournaments_file),
                    "--events-root", str(events_root), "--event-id", "10", "20",
                ])

            self.assertEqual(exit_code, 0)
            self.assertIn("Dry-run only", output)
            self.assertIn("num_entrants=9", output)
            self.assertIn("num_entrants=0", output)
            self.assertFalse(naive_dir.exists())
            with tournaments_file.open("r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('"event_id": 10', content)
            self.assertIn('"event_id": 20', content)

    def test_yes_redownloads_winner_and_removes_loser_registration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_root = root / "events"
            naive_dir = events_root / "Japan" / "2026" / "03" / "25" / "T" / "Singles"
            tournaments_file = self._setup_tournaments(root, naive_dir, naive_dir)

            write_attrs_calls = []

            def fake_write_attrs(*args, **kwargs):
                write_attrs_calls.append(args)

            with self._patched({10: 0, 20: 9}, attrs_mock=fake_write_attrs):
                exit_code, _output = self._run_main([
                    "--tournaments-file", str(tournaments_file),
                    "--events-root", str(events_root), "--event-id", "10", "20", "--yes",
                ])

            self.assertEqual(exit_code, 0)
            # write_event_attributes は勝者(event_id=20)についてのみ呼ばれる。
            self.assertEqual(len(write_attrs_calls), 1)
            self.assertEqual(write_attrs_calls[0][1], 20)
            self.assertTrue(naive_dir.is_dir())

            with tournaments_file.open("r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            by_tid = {e["tournament_id"]: e for e in lines}
            self.assertEqual(by_tid[2]["events"][0]["path"], str(naive_dir))
            self.assertEqual(by_tid[1]["events"], [])

    def test_yes_with_three_events_only_largest_survives(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_root = root / "events"
            naive_dir = events_root / "Japan" / "2026" / "03" / "25" / "T" / "Singles"
            tournaments_file = root / "tournaments.jsonl"
            self._write_tournaments(
                tournaments_file,
                [
                    {"tournament_id": 1, "name": "T", "events": [{"event_id": 10, "event_name": "Singles", "path": str(naive_dir)}]},
                    {"tournament_id": 2, "name": "T", "events": [{"event_id": 20, "event_name": "Singles", "path": str(naive_dir)}]},
                    {"tournament_id": 3, "name": "T", "events": [{"event_id": 30, "event_name": "Singles", "path": str(naive_dir)}]},
                ],
            )

            with self._patched({10: 0, 20: 9, 30: 0}):
                exit_code, output = self._run_main([
                    "--tournaments-file", str(tournaments_file),
                    "--events-root", str(events_root), "--event-id", "10", "20", "30", "--yes",
                ])

            self.assertEqual(exit_code, 0)
            self.assertIn("event_id=20", output)
            with tournaments_file.open("r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            by_tid = {e["tournament_id"]: e for e in lines}
            self.assertEqual(by_tid[2]["events"][0]["path"], str(naive_dir))
            self.assertEqual(by_tid[1]["events"], [])
            self.assertEqual(by_tid[3]["events"], [])

    def test_aborts_when_loser_has_nonzero_participants(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_root = root / "events"
            naive_dir = events_root / "Japan" / "2026" / "03" / "25" / "T" / "Singles"
            tournaments_file = self._setup_tournaments(root, naive_dir, naive_dir)

            with self._patched({10: 2, 20: 9}):
                exit_code, output = self._run_main([
                    "--tournaments-file", str(tournaments_file),
                    "--events-root", str(events_root), "--event-id", "10", "20", "--yes",
                ])

            self.assertEqual(exit_code, 1)
            self.assertIn("ABORT", output)
            self.assertFalse(naive_dir.exists())
            with tournaments_file.open("r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('"event_id": 10', content)
            self.assertIn('"event_id": 20', content)

    def test_treats_event_deleted_from_startgg_as_zero_participants(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_root = root / "events"
            naive_dir = events_root / "Japan" / "2026" / "03" / "25" / "T" / "Singles"
            tournaments_file = self._setup_tournaments(root, naive_dir, naive_dir)

            with self._patched({20: 9}, fetch_failed_event_ids={10}):
                exit_code, output = self._run_main([
                    "--tournaments-file", str(tournaments_file),
                    "--events-root", str(events_root), "--event-id", "10", "20", "--yes",
                ])

            self.assertEqual(exit_code, 0)
            self.assertIn("見つからず", output)
            with tournaments_file.open("r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            by_tid = {e["tournament_id"]: e for e in lines}
            self.assertEqual(by_tid[2]["events"][0]["path"], str(naive_dir))
            self.assertEqual(by_tid[1]["events"], [])

    def test_all_auto_discovers_and_fixes_every_collision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_root = root / "events"
            naive_dir_1 = events_root / "Japan" / "2026" / "03" / "25" / "T" / "Singles"
            naive_dir_2 = events_root / "Japan" / "2026" / "03" / "25" / "U" / "Doubles"
            tournaments_file = root / "tournaments.jsonl"
            self._write_tournaments(
                tournaments_file,
                [
                    {"tournament_id": 1, "name": "T", "events": [{"event_id": 10, "event_name": "Singles", "path": str(naive_dir_1)}]},
                    {"tournament_id": 2, "name": "T", "events": [{"event_id": 20, "event_name": "Singles", "path": str(naive_dir_1)}]},
                    {"tournament_id": 4, "name": "U", "events": [{"event_id": 40, "event_name": "Doubles", "path": str(naive_dir_2)}]},
                    {"tournament_id": 5, "name": "U", "events": [{"event_id": 50, "event_name": "Doubles", "path": str(naive_dir_2)}]},
                    {"tournament_id": 9, "name": "Solo", "events": [{"event_id": 90, "event_name": "Singles", "path": str(events_root / "Japan" / "2026" / "03" / "25" / "Solo" / "Singles")}]},
                ],
            )

            def fake_fetch_event_details(event_id):
                tid_and_name = {
                    10: (1, "T", "Singles"), 20: (2, "T", "Singles"),
                    40: (4, "U", "Doubles"), 50: (5, "U", "Doubles"),
                }[event_id]
                tid, tname, ename = tid_and_name
                return _fake_event_and_tournament(event_id, tid, tournament_name=tname, event_name=ename)

            def fake_download_standings(event_id, event_dir, max_pages=None):
                count = {10: 0, 20: 9, 40: 0, 50: 3}[event_id]
                return [None] * count, [None] * count, {}

            with patch.multiple(
                fpc,
                fetch_event_details=fake_fetch_event_details,
                download_standings=fake_download_standings,
                download_seeds=lambda *a, **k: None,
                download_all_set=lambda *a, **k: False,
                write_event_attributes=lambda *a, **k: None,
            ):
                exit_code, output = self._run_main([
                    "--tournaments-file", str(tournaments_file),
                    "--events-root", str(events_root), "--all", "--yes",
                ])

            self.assertEqual(exit_code, 0)
            self.assertIn("2件の衝突グループが見つかりました", output)
            with tournaments_file.open("r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            by_tid = {e["tournament_id"]: e for e in lines}
            # T グループ: event_id=20(参加者数9)が勝者。
            self.assertEqual(by_tid[2]["events"][0]["path"], str(naive_dir_1))
            self.assertEqual(by_tid[1]["events"], [])
            # U グループ: event_id=50(参加者数3)が勝者。
            self.assertEqual(by_tid[5]["events"][0]["path"], str(naive_dir_2))
            self.assertEqual(by_tid[4]["events"], [])
            # 衝突していないSoloは一切触られない。
            self.assertEqual(by_tid[9]["events"][0]["event_id"], 90)

    def test_all_continues_past_a_failed_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_root = root / "events"
            naive_dir_1 = events_root / "Japan" / "2026" / "03" / "25" / "T" / "Singles"
            naive_dir_2 = events_root / "Japan" / "2026" / "03" / "25" / "U" / "Doubles"
            tournaments_file = root / "tournaments.jsonl"
            self._write_tournaments(
                tournaments_file,
                [
                    {"tournament_id": 1, "name": "T", "events": [{"event_id": 10, "event_name": "Singles", "path": str(naive_dir_1)}]},
                    {"tournament_id": 2, "name": "T", "events": [{"event_id": 20, "event_name": "Singles", "path": str(naive_dir_1)}]},
                    {"tournament_id": 4, "name": "U", "events": [{"event_id": 40, "event_name": "Doubles", "path": str(naive_dir_2)}]},
                    {"tournament_id": 5, "name": "U", "events": [{"event_id": 50, "event_name": "Doubles", "path": str(naive_dir_2)}]},
                ],
            )

            def fake_fetch_event_details(event_id):
                tid_and_name = {
                    10: (1, "T", "Singles"), 20: (2, "T", "Singles"),
                    40: (4, "U", "Doubles"), 50: (5, "U", "Doubles"),
                }[event_id]
                tid, tname, ename = tid_and_name
                return _fake_event_and_tournament(event_id, tid, tournament_name=tname, event_name=ename)

            def fake_download_standings(event_id, event_dir, max_pages=None):
                # Tグループは敗者(10)が参加者数2で、安全確認に失敗するはず。
                # Uグループは正常に解決できるはず。
                count = {10: 2, 20: 9, 40: 0, 50: 3}[event_id]
                return [None] * count, [None] * count, {}

            with patch.multiple(
                fpc,
                fetch_event_details=fake_fetch_event_details,
                download_standings=fake_download_standings,
                download_seeds=lambda *a, **k: None,
                download_all_set=lambda *a, **k: False,
                write_event_attributes=lambda *a, **k: None,
            ):
                exit_code, output = self._run_main([
                    "--tournaments-file", str(tournaments_file),
                    "--events-root", str(events_root), "--all", "--yes",
                ])

            self.assertEqual(exit_code, 1)
            self.assertIn("ABORT", output)
            with tournaments_file.open("r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            by_tid = {e["tournament_id"]: e for e in lines}
            # Tグループは失敗したため両方とも変更されない。
            self.assertEqual(by_tid[1]["events"][0]["event_id"], 10)
            self.assertEqual(by_tid[2]["events"][0]["event_id"], 20)
            # Uグループは正常に解決される。
            self.assertEqual(by_tid[5]["events"][0]["path"], str(naive_dir_2))
            self.assertEqual(by_tid[4]["events"], [])

    def test_rejects_both_event_id_and_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file = Path(tmpdir) / "tournaments.jsonl"
            tournaments_file.write_text("", encoding="utf-8")
            exit_code, output = self._run_main([
                "--tournaments-file", str(tournaments_file),
                "--event-id", "10", "20", "--all",
            ])
            self.assertEqual(exit_code, 1)
            self.assertIn("どちらか一方", output)

    def test_rejects_neither_event_id_nor_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file = Path(tmpdir) / "tournaments.jsonl"
            tournaments_file.write_text("", encoding="utf-8")
            exit_code, output = self._run_main([
                "--tournaments-file", str(tournaments_file),
            ])
            self.assertEqual(exit_code, 1)
            self.assertIn("どちらか一方", output)

    def test_rejects_single_event_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournaments_file = Path(tmpdir) / "tournaments.jsonl"
            tournaments_file.write_text("", encoding="utf-8")
            exit_code, output = self._run_main([
                "--tournaments-file", str(tournaments_file),
                "--event-id", "10",
            ])
            self.assertEqual(exit_code, 1)
            self.assertIn("2件以上", output)


if __name__ == "__main__":
    unittest.main()
