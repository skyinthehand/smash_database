import json
import os
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from unittest.mock import patch

from scripts.fetch.download import (
    build_match_dedupe_key,
    configure_fetch_behavior,
    count_guest_entrants,
    dedupe_set_nodes,
    download_all_tournaments,
    fetch_all_phase_groups,
    fetch_all_sets,
    get_event_directory,
    load_excluded_phase_ids,
    should_skip_tournament,
    write_event_attributes,
    write_matches,
)
from scripts.utils import EVENT_DATA_VERSION, FetchError, read_json


class DownloadTests(unittest.TestCase):
    @patch("scripts.fetch.download.set_page_delay")
    @patch("scripts.fetch.download.set_retry_parameters")
    def test_configure_fetch_behavior_uses_faster_defaults_for_matches_only(
        self,
        mock_set_retry_parameters,
        mock_set_page_delay,
    ):
        args = Namespace(matches_only=True, max_retries=100, retry_delay=5)

        configure_fetch_behavior(args)

        mock_set_retry_parameters.assert_called_once_with(8, 2)
        mock_set_page_delay.assert_called_once_with(1)

    @patch("scripts.fetch.download.set_page_delay")
    @patch("scripts.fetch.download.set_retry_parameters")
    def test_configure_fetch_behavior_preserves_explicit_retry_settings_for_matches_only(
        self,
        mock_set_retry_parameters,
        mock_set_page_delay,
    ):
        args = Namespace(matches_only=True, max_retries=12, retry_delay=3)

        configure_fetch_behavior(args)

        mock_set_retry_parameters.assert_called_once_with(12, 3)
        mock_set_page_delay.assert_called_once_with(1)

    @patch("scripts.fetch.download.load_excluded_phase_ids", return_value={})
    @patch("scripts.fetch.download.fetch_all_nodes")
    def test_fetch_all_sets_retries_with_smaller_page_size_when_duplicate_ids_found(
        self, mock_fetch_all_nodes, _mock_load_excluded
    ):
        mock_fetch_all_nodes.side_effect = [
            [{"id": 1}, {"id": 1}, {"id": 2}],
            [{"id": 1}, {"id": 2}, {"id": 3}],
        ]

        sets_data = fetch_all_sets(1308799)

        self.assertEqual(sets_data, [{"id": 1}, {"id": 2}, {"id": 3}])
        self.assertEqual(mock_fetch_all_nodes.call_count, 2)
        self.assertEqual(mock_fetch_all_nodes.call_args_list[0].kwargs["per_page"], 50)
        self.assertEqual(mock_fetch_all_nodes.call_args_list[1].kwargs["per_page"], 25)

    def test_dedupe_set_nodes_removes_duplicate_set_ids_preserving_order(self):
        self.assertEqual(
            dedupe_set_nodes([{"id": 10}, {"id": 10}, {"id": 20}, {"name": "no-id"}]),
            [{"id": 10}, {"id": 20}, {"name": "no-id"}],
        )

    @patch("scripts.fetch.download.load_excluded_phase_ids", return_value={})
    @patch("scripts.fetch.download.fetch_all_nodes")
    def test_fetch_all_sets_retries_with_smaller_page_size_when_query_too_complex(
        self, mock_fetch_all_nodes, _mock_load_excluded
    ):
        mock_fetch_all_nodes.side_effect = [
            FetchError("query complexity is too high"),
            [{"id": 1}, {"id": 2}],
        ]

        sets_data = fetch_all_sets(1308799)

        self.assertEqual(sets_data, [{"id": 1}, {"id": 2}])
        self.assertEqual(mock_fetch_all_nodes.call_count, 2)
        self.assertEqual(mock_fetch_all_nodes.call_args_list[0].kwargs["per_page"], 50)
        self.assertEqual(mock_fetch_all_nodes.call_args_list[1].kwargs["per_page"], 25)

    @patch("scripts.fetch.download.load_excluded_phase_ids", return_value={})
    @patch("scripts.fetch.download._fetch_all_sets_by_phase_group")
    @patch("scripts.fetch.download.fetch_all_nodes")
    def test_fetch_all_sets_skips_event_level_when_excluded_phase_configured(
        self, mock_fetch_all_nodes, mock_by_phase_group, mock_load_excluded
    ):
        mock_load_excluded.return_value = {436192: {731718}}
        mock_by_phase_group.return_value = [{"id": 1}]

        sets_data = fetch_all_sets(436192)

        self.assertEqual(sets_data, [{"id": 1}])
        mock_fetch_all_nodes.assert_not_called()
        mock_by_phase_group.assert_called_once_with(436192, {731718}, lightweight=False, max_pages=None)

    @patch("scripts.fetch.download.load_excluded_phase_ids", return_value={})
    @patch("scripts.fetch.download._fetch_all_sets_by_phase_group")
    @patch("scripts.fetch.download.fetch_all_nodes")
    def test_fetch_all_sets_falls_back_to_phase_group_when_event_level_unresolvable(
        self, mock_fetch_all_nodes, mock_by_phase_group, _mock_load_excluded
    ):
        # per_page を全通り試しても重複が解消せず、total とも一致しないケース。
        mock_fetch_all_nodes.side_effect = [
            [{"id": 1}, {"id": 1}] for _ in range(len(("50", "25", "10", "5", "3", "1")))
        ]
        mock_by_phase_group.return_value = [{"id": 1}, {"id": 2}]

        sets_data = fetch_all_sets(436192)

        self.assertEqual(sets_data, [{"id": 1}, {"id": 2}])
        mock_by_phase_group.assert_called_once_with(436192, set(), lightweight=False, max_pages=None)

    @patch("scripts.fetch.download.fetch_all_phase_groups")
    @patch("scripts.fetch.download.fetch_all_nodes")
    def test_fetch_all_sets_by_phase_group_excludes_configured_phase_groups(
        self, mock_fetch_all_nodes, mock_fetch_all_phase_groups
    ):
        from scripts.fetch.download import _fetch_all_sets_by_phase_group

        mock_fetch_all_phase_groups.return_value = [
            (731718, 111, "Bad Pool"),
            (999999, 222, "Good Pool"),
        ]
        mock_fetch_all_nodes.return_value = [{"id": 5}]

        sets_data = _fetch_all_sets_by_phase_group(436192, {731718})

        self.assertEqual(sets_data, [{"id": 5}])
        mock_fetch_all_nodes.assert_called_once()
        self.assertEqual(mock_fetch_all_nodes.call_args.args[1], {"phaseGroupId": 222})

    @patch("scripts.fetch.download.fetch_all_phase_groups")
    def test_fetch_all_sets_by_phase_group_raises_when_all_groups_excluded(self, mock_fetch_all_phase_groups):
        from scripts.fetch.download import _fetch_all_sets_by_phase_group

        mock_fetch_all_phase_groups.return_value = [(731718, 111, "Bad Pool")]

        with self.assertRaises(FetchError):
            _fetch_all_sets_by_phase_group(436192, {731718})

    @patch("scripts.fetch.download.time.sleep")
    @patch("scripts.fetch.download.fetch_data_with_retries")
    def test_fetch_all_phase_groups_paginates_until_all_phases_exhausted(self, mock_fetch, _mock_sleep):
        mock_fetch.side_effect = [
            {
                "data": {
                    "event": {
                        "phases": [
                            {
                                "id": 1,
                                "phaseGroups": {
                                    "pageInfo": {"total": 2},
                                    "nodes": [{"id": 10, "displayIdentifier": "A"}],
                                },
                            },
                            {
                                "id": 2,
                                "phaseGroups": {
                                    "pageInfo": {"total": 1},
                                    "nodes": [{"id": 20, "displayIdentifier": "B"}],
                                },
                            },
                        ]
                    }
                }
            },
            {
                "data": {
                    "event": {
                        "phases": [
                            {
                                "id": 1,
                                "phaseGroups": {
                                    "pageInfo": {"total": 2},
                                    "nodes": [{"id": 11, "displayIdentifier": "A2"}],
                                },
                            },
                            {
                                "id": 2,
                                "phaseGroups": {
                                    "pageInfo": {"total": 1},
                                    "nodes": [],
                                },
                            },
                        ]
                    }
                }
            },
        ]

        result = fetch_all_phase_groups(436192)

        self.assertEqual(
            sorted(result),
            sorted([(1, 10, "A"), (1, 11, "A2"), (2, 20, "B")]),
        )
        self.assertEqual(mock_fetch.call_count, 2)

    def test_load_excluded_phase_ids_reads_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "excluded_phases.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"436192": [{"phase_id": 731718, "reason": "test"}]}, f)

            result = load_excluded_phase_ids(path)

            self.assertEqual(result, {436192: {731718}})

    def test_load_excluded_phase_ids_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "does_not_exist.json")

            self.assertEqual(load_excluded_phase_ids(path), {})

    def test_build_match_dedupe_key_ignores_details(self):
        base = {
            "winner_id": 1,
            "loser_id": 2,
            "winner_score": 2,
            "loser_score": 1,
            "round_text": "Winners Round 1",
            "round": 1,
            "phase": "B1200",
            "wave": "B",
            "dq": False,
            "cancel": False,
            "state": 3,
            "details": [{"game_id": 10}],
        }
        variant = dict(base)
        variant["details"] = [{"game_id": 11}]
        self.assertEqual(build_match_dedupe_key(base), build_match_dedupe_key(variant))

    def test_write_event_attributes_includes_version_and_guest_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            place = {
                "country_code": "JP",
                "city": "Tokyo",
                "lat": 0,
                "lng": 0,
                "venue_name": "v",
                "timezone": "Asia/Tokyo",
                "postal_code": "p",
                "venue_address": "a",
                "maps_place_id": "m",
            }
            write_event_attributes(
                10, 999, "Event", "Tournament", 1710001000, place,
                "https://example.com", {}, True, tmpdir,
                guest_entrant_count=3,
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
            self.assertEqual(attr["event_data_version"], EVENT_DATA_VERSION)
            self.assertEqual(attr["guest_entrant_count"], 3)

    def test_write_event_attributes_includes_end_at(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            place = {
                "country_code": "JP",
                "city": "Tokyo",
                "lat": 0,
                "lng": 0,
                "venue_name": "v",
                "timezone": "Asia/Tokyo",
                "postal_code": "p",
                "venue_address": "a",
                "maps_place_id": "m",
            }
            write_event_attributes(
                10, 999, "Event", "Tournament", 1710001000, place,
                "https://example.com", {}, True, tmpdir,
                guest_entrant_count=3,
                end_at=1710086400,
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
            self.assertEqual(attr["end_at"], 1710086400)

    def test_write_event_attributes_end_at_defaults_to_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            place = {
                "country_code": "JP",
                "city": "Tokyo",
                "lat": 0,
                "lng": 0,
                "venue_name": "v",
                "timezone": "Asia/Tokyo",
                "postal_code": "p",
                "venue_address": "a",
                "maps_place_id": "m",
            }
            write_event_attributes(
                10, 999, "Event", "Tournament", 1710001000, place,
                "https://example.com", {}, True, tmpdir,
                guest_entrant_count=3,
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
            self.assertIsNone(attr["end_at"])

    def test_count_guest_entrants_counts_none_users(self):
        user_data = [{"id": 1}, None, {"id": 2}, None, None]
        self.assertEqual(count_guest_entrants(user_data), 3)

    def test_count_guest_entrants_zero_when_no_guests(self):
        user_data = [{"id": 1}, {"id": 2}]
        self.assertEqual(count_guest_entrants(user_data), 0)

    def test_write_matches_dedupes_semantically_identical_matches(self):
        node = {
            "id": 101,
            "slots": [
                {
                    "entrant": {"id": 11},
                    "standing": {"stats": {"score": {"value": 2}}},
                },
                {
                    "entrant": {"id": 22},
                    "standing": {"stats": {"score": {"value": 0}}},
                },
            ],
            "games": None,
            "phaseGroup": {"displayIdentifier": "B1200", "wave": {"identifier": "B"}},
            "fullRoundText": "Winners Round 1",
            "round": 1,
            "state": 3,
        }
        duplicate_with_different_id = dict(node)
        duplicate_with_different_id["id"] = 202

        with tempfile.TemporaryDirectory() as tmpdir:
            write_matches([node, duplicate_with_different_id], {11: 2716511, 22: 2962327}, tmpdir)
            with open(f"{tmpdir}/matches.json", encoding="utf-8") as fh:
                payload = json.load(fh)

        self.assertEqual(len(payload["data"]), 1)

    def test_should_skip_tournament_when_done_and_complete(self):
        tournaments = {
            1: {
                "events": [
                    {"path": "event-dir"},
                ]
            }
        }

        with patch("scripts.fetch.download.event_files_complete", return_value=True):
            self.assertTrue(should_skip_tournament(1, tournaments, {1}, force_refresh=False))

    def test_should_not_skip_tournament_when_force_refresh_enabled(self):
        tournaments = {
            1: {
                "events": [
                    {"path": "event-dir"},
                ]
            }
        }

        with patch("scripts.fetch.download.event_files_complete", return_value=True):
            self.assertFalse(should_skip_tournament(1, tournaments, {1}, force_refresh=True))

    def test_should_not_skip_tournament_when_missing_files(self):
        tournaments = {
            1: {
                "events": [
                    {"path": "event-dir"},
                ]
            }
        }

        with patch("scripts.fetch.download.event_files_complete", return_value=False):
            self.assertFalse(should_skip_tournament(1, tournaments, {1}, force_refresh=False))

    @patch("scripts.fetch.download.read_set", return_value=set())
    @patch("scripts.fetch.download.read_users_jsonl", return_value={})
    @patch("scripts.fetch.download.read_tournaments_jsonl", return_value={})
    @patch("scripts.fetch.download.fetch_latest_tournaments_by_game")
    @patch("scripts.fetch.download.fetch_event_ids_from_tournament")
    @patch("scripts.fetch.download.fetch_entrant_user_map")
    @patch("scripts.fetch.download.download_all_set")
    @patch("scripts.fetch.download.download_standings")
    @patch("scripts.fetch.download.download_seeds")
    @patch("scripts.fetch.download.extend_user_info")
    @patch("scripts.fetch.download.extend_tournament_info")
    @patch("scripts.fetch.download.write_done_tournaments")
    def test_download_all_tournaments_matches_only_skips_heavy_fetches(
        self,
        mock_write_done,
        mock_extend_tournament,
        mock_extend_user_info,
        mock_download_seeds,
        mock_download_standings,
        mock_download_all_set,
        mock_fetch_entrant_user_map,
        mock_fetch_event_ids,
        mock_fetch_tournaments,
        _mock_read_tournaments,
        _mock_read_users,
        _mock_read_set,
    ):
        mock_fetch_tournaments.return_value = (
            [
                {
                    "id": 1,
                    "name": "Test Tournament",
                    "startAt": 1714780800,
                    "endAt": 1714784400,
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
                }
            ],
            1,
        )
        mock_fetch_event_ids.return_value = [(10, "Singles", False)]
        mock_fetch_entrant_user_map.return_value = {11: 2716511}

        with tempfile.TemporaryDirectory() as tmpdir:
            event_dir = get_event_directory(
                f"{tmpdir}",
                "JP",
                "2024",
                "05",
                "04",
                "Test Tournament",
                "Singles",
            )
            os.makedirs(event_dir, exist_ok=True)
            download_all_tournaments(
                "1386",
                "JP",
                datetime(2024, 5, 4, 23, 59, 59),
                datetime(2024, 5, 4, 0, 0, 0),
                f"{tmpdir}",
                f"{tmpdir}/done.csv",
                f"{tmpdir}/users.jsonl",
                f"{tmpdir}/tournaments.jsonl",
                force_refresh=True,
                matches_only=True,
            )

        mock_fetch_entrant_user_map.assert_called_once_with(10)
        mock_download_all_set.assert_called_once_with(10, {11: 2716511}, event_dir, lightweight=True)
        mock_download_standings.assert_not_called()
        mock_download_seeds.assert_not_called()
        mock_extend_user_info.assert_not_called()
        mock_extend_tournament.assert_not_called()
        mock_write_done.assert_not_called()


if __name__ == "__main__":
    unittest.main()
