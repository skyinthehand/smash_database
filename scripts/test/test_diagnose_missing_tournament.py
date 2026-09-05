import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from scripts.fix import diagnose_missing_tournament as dmt
from scripts.utils import FetchError, NoEventsForGameError


def _fake_event(event_id=999, state="COMPLETED", start_at=1700000000, tournament_overrides=None):
    tournament = {
        "id": 555,
        "name": "Grand Wars 3",
        "slug": "grand-wars-3-maesuma-grand-wars-3",
        "url": "https://start.gg/tournament/x",
        "countryCode": "JP",
        "city": "Osaka",
        "lat": 0,
        "lng": 0,
        "venueName": "v",
        "timezone": "Asia/Tokyo",
        "postalCode": None,
        "venueAddress": None,
        "mapsPlaceId": None,
        "endAt": 1700003600,
    }
    if tournament_overrides:
        tournament.update(tournament_overrides)
    return {
        "id": event_id,
        "name": "Singles Tournament",
        "startAt": start_at,
        "isOnline": False,
        "numEntrants": 32,
        "state": state,
        "type": 1,
        "tournament": tournament,
    }


class ParseArgsTests(unittest.TestCase):
    def test_extracts_slugs_from_url(self):
        with patch.object(
            dmt.sys, "argv",
            ["x", "--token", "T", "--url",
             "https://www.start.gg/tournament/grand-wars-3-maesuma-grand-wars-3/event/singles-tournament"],
        ):
            args = dmt.parse_args()
        self.assertEqual(args.tournament_slug, "grand-wars-3-maesuma-grand-wars-3")
        self.assertEqual(args.event_slug, "singles-tournament")

    def test_accepts_explicit_slugs(self):
        with patch.object(dmt.sys, "argv", ["x", "--token", "T", "--tournament-slug", "a", "--event-slug", "b"]):
            args = dmt.parse_args()
        self.assertEqual((args.tournament_slug, args.event_slug), ("a", "b"))

    def test_malformed_url_errors(self):
        with patch.object(dmt.sys, "argv", ["x", "--token", "T", "--url", "https://www.start.gg/not-a-tournament-url"]):
            with self.assertRaises(SystemExit):
                dmt.parse_args()

    def test_missing_slugs_errors(self):
        with patch.object(dmt.sys, "argv", ["x", "--token", "T"]):
            with self.assertRaises(SystemExit):
                dmt.parse_args()


class MainDiagnosisTests(unittest.TestCase):
    def _run(self, event, game_events=None, game_error=None, extra_args=None):
        argv = ["x", "--token", "T", "--tournament-slug", "t", "--event-slug", "e"] + (extra_args or [])
        buf = io.StringIO()
        err = io.StringIO()

        def fake_fetch_event_ids(tournament_id, game_id):
            if game_error is not None:
                raise game_error
            return game_events if game_events is not None else [(event["id"], "Singles Tournament", False, "COMPLETED", 1)]

        with patch.object(dmt.sys, "argv", argv), \
             patch.object(dmt, "fetch_event_details_by_slug", return_value=event), \
             patch.object(dmt, "set_api_parameters"), patch.object(dmt, "set_retry_parameters"), \
             patch.object(dmt, "fetch_event_ids_from_tournament", side_effect=fake_fetch_event_ids), \
             redirect_stdout(buf), redirect_stderr(err):
            exit_code = dmt.main()
        return exit_code, buf.getvalue(), err.getvalue()

    def test_lookup_failure_returns_error(self):
        argv = ["x", "--token", "T", "--tournament-slug", "t", "--event-slug", "e"]
        err = io.StringIO()
        with patch.object(dmt.sys, "argv", argv), \
             patch.object(dmt, "fetch_event_details_by_slug", return_value=None), \
             patch.object(dmt, "set_api_parameters"), patch.object(dmt, "set_retry_parameters"), \
             redirect_stdout(io.StringIO()), redirect_stderr(err):
            exit_code = dmt.main()
        self.assertEqual(exit_code, 1)
        self.assertIn("取得できませんでした", err.getvalue())

    def test_not_yet_finished_is_reported(self):
        event = _fake_event(tournament_overrides={"endAt": None})
        exit_code, out, _err = self._run(event)
        self.assertEqual(exit_code, 0)
        self.assertIn("まだ終了していません", out)

    def test_country_code_mismatch_is_reported(self):
        event = _fake_event(tournament_overrides={"countryCode": "US"})
        exit_code, out, _err = self._run(event)
        self.assertEqual(exit_code, 0)
        self.assertIn("countryCode", out)
        self.assertIn("'US'", out)

    def test_no_events_for_game_is_reported(self):
        event = _fake_event()
        exit_code, out, _err = self._run(event, game_error=NoEventsForGameError("no events"))
        self.assertEqual(exit_code, 0)
        self.assertIn("紐づくイベントが1件もありません", out)

    def test_event_not_in_game_event_list_is_reported(self):
        event = _fake_event(event_id=999)
        exit_code, out, _err = self._run(event, game_events=[(111, "Other Event", False, "COMPLETED", 1)])
        self.assertEqual(exit_code, 0)
        self.assertIn("含まれていません", out)

    def test_generic_fetch_error_during_game_check_is_reported(self):
        event = _fake_event()
        exit_code, out, _err = self._run(event, game_error=FetchError("boom"))
        self.assertEqual(exit_code, 0)
        self.assertIn("エラーが発生しました", out)

    def test_no_known_reason_found_suggests_manual_fetch(self):
        event = _fake_event()
        exit_code, out, _err = self._run(event)
        self.assertEqual(exit_code, 0)
        self.assertIn("該当しませんでした", out)
        self.assertIn("download_specific_event.py", out)

    def test_already_registered_locally_is_reported(self):
        event = _fake_event(event_id=999)
        with patch.object(
            dmt, "read_tournaments_jsonl",
            return_value={555: {"tournament_id": 555, "events": [{"event_id": 999, "path": "x"}]}},
        ):
            exit_code, out, _err = self._run(event)
        self.assertEqual(exit_code, 0)
        self.assertIn("既に", out)
        self.assertIn("登録済み", out)


if __name__ == "__main__":
    unittest.main()
