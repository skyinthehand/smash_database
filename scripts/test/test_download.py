import calendar
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
    download_by_ids,
    fetch_all_phase_groups,
    fetch_all_sets,
    fetch_event_ids_from_tournament,
    get_event_directory,
    load_excluded_phase_ids,
    record_event_path,
    should_skip_tournament,
    write_event_attributes,
    write_matches,
)
from scripts.utils import (
    EVENT_DATA_VERSION,
    FetchError,
    MaxPagesExceededError,
    NoEventsForGameError,
    read_json,
    read_tournaments_jsonl,
)


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

    def test_write_event_attributes_includes_state_and_renamed_archive_status(self):
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
                state="COMPLETED",
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
            self.assertEqual(attr["state"], "COMPLETED")
            self.assertEqual(attr["archive_status"], "completed")
            self.assertNotIn("status", attr)

    def test_write_event_attributes_state_defaults_to_none(self):
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
            self.assertIsNone(attr["state"])

    def test_write_event_attributes_includes_type(self):
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
                event_type=1,
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
            self.assertEqual(attr["type"], 1)

    def test_write_event_attributes_type_defaults_to_none(self):
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
            self.assertIsNone(attr["type"])

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

    def test_should_not_skip_tournament_when_recorded_date_differs_from_current(self):
        tournaments = {
            1: {
                "events": [
                    {"path": "data/startgg/events/Japan/2025/08/16/T/E"},
                ]
            }
        }

        with patch("scripts.fetch.download.event_files_complete", return_value=True):
            self.assertFalse(
                should_skip_tournament(
                    1, tournaments, {1}, force_refresh=False,
                    current_date_parts=("2026", "02", "07"),
                )
            )

    def test_should_skip_tournament_when_recorded_date_matches_current(self):
        tournaments = {
            1: {
                "events": [
                    {"path": "data/startgg/events/Japan/2025/08/16/T/E"},
                ]
            }
        }

        with patch("scripts.fetch.download.event_files_complete", return_value=True):
            self.assertTrue(
                should_skip_tournament(
                    1, tournaments, {1}, force_refresh=False,
                    current_date_parts=("2025", "08", "16"),
                )
            )

    @patch("scripts.fetch.download.fetch_data_with_retries")
    def test_fetch_event_ids_from_tournament_raises_no_events_error_when_events_null_without_graphql_errors(
        self, mock_fetch
    ):
        # errors が無いのに events だけ null ということは、クエリは正常完了した上で
        # 対象ゲームのイベントが0件だったと判断できる → 専用の例外(NoEventsForGameError)。
        mock_fetch.return_value = {
            "data": {"tournament": {"id": 811466, "name": "Test Tournament", "events": None}}
        }

        with self.assertRaises(NoEventsForGameError):
            fetch_event_ids_from_tournament(811466, "1386")

    @patch("scripts.fetch.download.fetch_data_with_retries")
    def test_fetch_event_ids_from_tournament_raises_plain_fetch_error_when_events_null_with_graphql_errors(
        self, mock_fetch
    ):
        # errors が付いている場合は解決に失敗した(=確認不能)ため、区別せず通常のFetchError。
        mock_fetch.return_value = {
            "data": {"tournament": {"id": 811466, "name": "Test Tournament", "events": None}},
            "errors": [{"message": "internal error resolving events"}],
        }

        with self.assertRaises(FetchError) as ctx:
            fetch_event_ids_from_tournament(811466, "1386")
        self.assertNotIsInstance(ctx.exception, NoEventsForGameError)

    @patch("scripts.fetch.download.fetch_data_with_retries")
    def test_fetch_event_ids_from_tournament_includes_state(self, mock_fetch):
        mock_fetch.return_value = {
            "data": {
                "tournament": {
                    "id": 811466,
                    "name": "Test Tournament",
                    "events": [
                        {"id": 10, "name": "Singles", "isOnline": False, "state": "COMPLETED", "type": 1},
                    ],
                }
            }
        }

        self.assertEqual(
            fetch_event_ids_from_tournament(811466, "1386"),
            [(10, "Singles", False, "COMPLETED", 1)],
        )

    # -- record_event_path (US1/US3 共有ヘルパー) ---------------------------

    def test_record_event_path_appends_new_entry(self):
        tournaments = {1: {"tournament_id": 1, "name": "T", "events": []}}

        changed = record_event_path(tournaments, 1, 10, "Singles", "new-dir")

        self.assertTrue(changed)
        self.assertEqual(
            tournaments[1]["events"],
            [{"event_id": 10, "event_name": "Singles", "path": "new-dir"}],
        )

    def test_record_event_path_does_not_append_when_matches_only(self):
        tournaments = {1: {"tournament_id": 1, "name": "T", "events": []}}

        changed = record_event_path(tournaments, 1, 10, "Singles", "new-dir", matches_only=True)

        self.assertFalse(changed)
        self.assertEqual(tournaments[1]["events"], [])

    def test_record_event_path_is_noop_when_path_unchanged(self):
        tournaments = {
            1: {"tournament_id": 1, "name": "T", "events": [{"event_id": 10, "event_name": "Singles", "path": "same-dir"}]}
        }

        with patch("scripts.fetch.download.event_files_complete", return_value=True) as mock_complete:
            changed = record_event_path(tournaments, 1, 10, "Singles", "same-dir")

        self.assertFalse(changed)
        mock_complete.assert_not_called()

    def test_record_event_path_relocates_when_new_directory_is_complete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_dir = os.path.join(tmpdir, "old")
            new_dir = os.path.join(tmpdir, "new")
            os.makedirs(old_dir, exist_ok=True)
            with open(os.path.join(old_dir, "marker.json"), "w", encoding="utf-8") as f:
                f.write("{}")

            tournaments = {
                1: {"tournament_id": 1, "name": "T", "events": [{"event_id": 10, "event_name": "Singles", "path": old_dir}]}
            }

            with patch("scripts.fetch.download.event_files_complete", return_value=True):
                changed = record_event_path(tournaments, 1, 10, "Singles", new_dir)

            self.assertTrue(changed)
            self.assertEqual(tournaments[1]["events"][0]["path"], new_dir)
            self.assertFalse(os.path.isdir(old_dir))

    def test_record_event_path_keeps_old_directory_when_new_directory_incomplete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_dir = os.path.join(tmpdir, "old")
            new_dir = os.path.join(tmpdir, "new")
            os.makedirs(old_dir, exist_ok=True)

            tournaments = {
                1: {"tournament_id": 1, "name": "T", "events": [{"event_id": 10, "event_name": "Singles", "path": old_dir}]}
            }

            with patch("scripts.fetch.download.event_files_complete", return_value=False):
                changed = record_event_path(tournaments, 1, 10, "Singles", new_dir)

            self.assertFalse(changed)
            self.assertEqual(tournaments[1]["events"][0]["path"], old_dir)
            self.assertTrue(os.path.isdir(old_dir))

    def test_record_event_path_does_not_touch_unrelated_event_id(self):
        # FR-008: たまたま別イベントが記録されていても、異なる event_id は重複とみなさない。
        tournaments = {
            1: {
                "tournament_id": 1,
                "name": "T",
                "events": [{"event_id": 99, "event_name": "Singles", "path": "unrelated-dir"}],
            }
        }

        with patch("scripts.fetch.download.event_files_complete", return_value=True):
            changed = record_event_path(tournaments, 1, 100, "Doubles", "another-dir")

        self.assertTrue(changed)
        self.assertEqual(
            tournaments[1]["events"],
            [
                {"event_id": 99, "event_name": "Singles", "path": "unrelated-dir"},
                {"event_id": 100, "event_name": "Doubles", "path": "another-dir"},
            ],
        )

    @patch("scripts.fetch.download.event_files_complete", return_value=True)
    @patch("scripts.fetch.download.read_set", return_value=set())
    @patch("scripts.fetch.download.read_users_jsonl", return_value={})
    @patch("scripts.fetch.download.fetch_latest_tournaments_by_game")
    @patch("scripts.fetch.download.fetch_event_ids_from_tournament")
    @patch("scripts.fetch.download.download_all_set")
    @patch("scripts.fetch.download.download_standings")
    @patch("scripts.fetch.download.download_seeds")
    @patch("scripts.fetch.download.extend_user_info")
    @patch("scripts.fetch.download.write_done_tournaments")
    def test_download_all_tournaments_relocates_event_when_start_date_changes(
        self,
        _mock_write_done,
        _mock_extend_user_info,
        _mock_download_seeds,
        mock_download_standings,
        _mock_download_all_set,
        mock_fetch_event_ids,
        mock_fetch_tournaments,
        _mock_read_users,
        _mock_read_set,
        _mock_event_files_complete,
    ):
        new_start = calendar.timegm((2026, 2, 7, 9, 0, 0, 0, 0, 0))
        new_end = calendar.timegm((2026, 2, 7, 12, 0, 0, 0, 0, 0))
        mock_fetch_tournaments.return_value = (
            [
                {
                    "id": 1,
                    "name": "Test Tournament",
                    "startAt": new_start,
                    "endAt": new_end,
                    "countryCode": "JP",
                    "city": "Chiba",
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
        mock_fetch_event_ids.return_value = [(10, "Singles", False, "COMPLETED", 1)]
        mock_download_standings.return_value = ([], [], {})

        with tempfile.TemporaryDirectory() as tmpdir:
            old_event_dir = get_event_directory(tmpdir, "JP", "2025", "08", "16", "Test Tournament", "Singles")
            os.makedirs(old_event_dir, exist_ok=True)
            with open(os.path.join(old_event_dir, "marker.json"), "w", encoding="utf-8") as f:
                f.write("{}")

            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            with open(tournament_file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "tournament_id": 1,
                        "name": "Test Tournament",
                        "events": [{"event_id": 10, "event_name": "Singles", "path": old_event_dir}],
                        "version": "1.0",
                    },
                    f,
                )
                f.write("\n")

            new_event_dir = get_event_directory(tmpdir, "JP", "2026", "02", "07", "Test Tournament", "Singles")
            os.makedirs(new_event_dir, exist_ok=True)

            download_all_tournaments(
                "1386",
                "JP",
                datetime(2026, 2, 7, 23, 59, 59),
                datetime(2026, 2, 7, 0, 0, 0),
                f"{tmpdir}",
                f"{tmpdir}/done.csv",
                f"{tmpdir}/users.jsonl",
                tournament_file_path,
                force_refresh=True,
            )

            self.assertFalse(os.path.isdir(old_event_dir))
            self.assertTrue(os.path.isfile(os.path.join(new_event_dir, "attr.json")))

            updated = read_tournaments_jsonl(tournament_file_path)
            self.assertEqual(updated[1]["events"][0]["path"], new_event_dir)

    @patch("scripts.fetch.download.event_files_complete", return_value=False)
    @patch("scripts.fetch.download.read_set", return_value=set())
    @patch("scripts.fetch.download.read_users_jsonl", return_value={})
    @patch("scripts.fetch.download.fetch_latest_tournaments_by_game")
    @patch("scripts.fetch.download.fetch_event_ids_from_tournament")
    @patch("scripts.fetch.download.download_all_set")
    @patch("scripts.fetch.download.download_standings")
    @patch("scripts.fetch.download.download_seeds")
    @patch("scripts.fetch.download.extend_user_info")
    @patch("scripts.fetch.download.write_done_tournaments")
    def test_download_all_tournaments_keeps_old_directory_when_new_directory_incomplete(
        self,
        _mock_write_done,
        _mock_extend_user_info,
        _mock_download_seeds,
        mock_download_standings,
        _mock_download_all_set,
        mock_fetch_event_ids,
        mock_fetch_tournaments,
        _mock_read_users,
        _mock_read_set,
        _mock_event_files_complete,
    ):
        new_start = calendar.timegm((2026, 2, 7, 9, 0, 0, 0, 0, 0))
        new_end = calendar.timegm((2026, 2, 7, 12, 0, 0, 0, 0, 0))
        mock_fetch_tournaments.return_value = (
            [
                {
                    "id": 1,
                    "name": "Test Tournament",
                    "startAt": new_start,
                    "endAt": new_end,
                    "countryCode": "JP",
                    "city": "Chiba",
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
        mock_fetch_event_ids.return_value = [(10, "Singles", False, "COMPLETED", 1)]
        mock_download_standings.return_value = ([], [], {})

        with tempfile.TemporaryDirectory() as tmpdir:
            old_event_dir = get_event_directory(tmpdir, "JP", "2025", "08", "16", "Test Tournament", "Singles")
            os.makedirs(old_event_dir, exist_ok=True)
            with open(os.path.join(old_event_dir, "marker.json"), "w", encoding="utf-8") as f:
                f.write("{}")

            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            with open(tournament_file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "tournament_id": 1,
                        "name": "Test Tournament",
                        "events": [{"event_id": 10, "event_name": "Singles", "path": old_event_dir}],
                        "version": "1.0",
                    },
                    f,
                )
                f.write("\n")

            new_event_dir = get_event_directory(tmpdir, "JP", "2026", "02", "07", "Test Tournament", "Singles")
            os.makedirs(new_event_dir, exist_ok=True)

            download_all_tournaments(
                "1386",
                "JP",
                datetime(2026, 2, 7, 23, 59, 59),
                datetime(2026, 2, 7, 0, 0, 0),
                f"{tmpdir}",
                f"{tmpdir}/done.csv",
                f"{tmpdir}/users.jsonl",
                tournament_file_path,
                force_refresh=True,
            )

            self.assertTrue(os.path.isdir(old_event_dir))
            updated = read_tournaments_jsonl(tournament_file_path)
            self.assertEqual(updated[1]["events"][0]["path"], old_event_dir)

    @patch("scripts.fetch.download.event_files_complete", return_value=True)
    @patch("scripts.fetch.download.read_set", return_value=set())
    @patch("scripts.fetch.download.read_users_jsonl", return_value={})
    @patch("scripts.fetch.download.fetch_latest_tournaments_by_game")
    @patch("scripts.fetch.download.fetch_event_ids_from_tournament")
    @patch("scripts.fetch.download.download_all_set")
    @patch("scripts.fetch.download.download_standings")
    @patch("scripts.fetch.download.download_seeds")
    @patch("scripts.fetch.download.extend_user_info")
    @patch("scripts.fetch.download.write_done_tournaments")
    def test_download_all_tournaments_does_not_touch_untracked_duplicate_directory(
        self,
        _mock_write_done,
        _mock_extend_user_info,
        _mock_download_seeds,
        mock_download_standings,
        _mock_download_all_set,
        mock_fetch_event_ids,
        mock_fetch_tournaments,
        _mock_read_users,
        _mock_read_set,
        _mock_event_files_complete,
    ):
        # 3件以上重複しているケース(tournaments.jsonlが参照しているのは1件のみ)で、
        # どこからも参照されていない中間ディレクトリには手を出さないことを確認する(Edge Case)。
        new_start = calendar.timegm((2026, 2, 7, 9, 0, 0, 0, 0, 0))
        new_end = calendar.timegm((2026, 2, 7, 12, 0, 0, 0, 0, 0))
        mock_fetch_tournaments.return_value = (
            [
                {
                    "id": 1,
                    "name": "Test Tournament",
                    "startAt": new_start,
                    "endAt": new_end,
                    "countryCode": "JP",
                    "city": "Chiba",
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
        mock_fetch_event_ids.return_value = [(10, "Singles", False, "COMPLETED", 1)]
        mock_download_standings.return_value = ([], [], {})

        with tempfile.TemporaryDirectory() as tmpdir:
            tracked_old_dir = get_event_directory(tmpdir, "JP", "2025", "08", "16", "Test Tournament", "Singles")
            untracked_middle_dir = get_event_directory(tmpdir, "JP", "2025", "11", "01", "Test Tournament", "Singles")
            os.makedirs(tracked_old_dir, exist_ok=True)
            os.makedirs(untracked_middle_dir, exist_ok=True)
            with open(os.path.join(untracked_middle_dir, "marker.json"), "w", encoding="utf-8") as f:
                f.write("{}")

            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            with open(tournament_file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "tournament_id": 1,
                        "name": "Test Tournament",
                        "events": [{"event_id": 10, "event_name": "Singles", "path": tracked_old_dir}],
                        "version": "1.0",
                    },
                    f,
                )
                f.write("\n")

            new_event_dir = get_event_directory(tmpdir, "JP", "2026", "02", "07", "Test Tournament", "Singles")
            os.makedirs(new_event_dir, exist_ok=True)

            download_all_tournaments(
                "1386",
                "JP",
                datetime(2026, 2, 7, 23, 59, 59),
                datetime(2026, 2, 7, 0, 0, 0),
                f"{tmpdir}",
                f"{tmpdir}/done.csv",
                f"{tmpdir}/users.jsonl",
                tournament_file_path,
                force_refresh=True,
            )

            self.assertFalse(os.path.isdir(tracked_old_dir))
            self.assertTrue(os.path.isdir(untracked_middle_dir))

    @patch("scripts.fetch.download.event_files_complete", return_value=True)
    @patch("scripts.fetch.download.read_set", return_value=set())
    @patch("scripts.fetch.download.read_users_jsonl", return_value={})
    @patch("scripts.fetch.download.fetch_tournament_by_id")
    @patch("scripts.fetch.download.fetch_event_ids_from_tournament")
    @patch("scripts.fetch.download.download_all_set")
    @patch("scripts.fetch.download.download_standings")
    @patch("scripts.fetch.download.download_seeds")
    @patch("scripts.fetch.download.extend_user_info")
    @patch("scripts.fetch.download.write_done_tournaments")
    def test_download_by_ids_relocates_event_via_shared_helper(
        self,
        _mock_write_done,
        _mock_extend_user_info,
        _mock_download_seeds,
        mock_download_standings,
        _mock_download_all_set,
        mock_fetch_event_ids,
        mock_fetch_tournament_by_id,
        _mock_read_users,
        _mock_read_set,
        _mock_event_files_complete,
    ):
        new_start = calendar.timegm((2026, 2, 7, 9, 0, 0, 0, 0, 0))
        new_end = calendar.timegm((2026, 2, 7, 12, 0, 0, 0, 0, 0))
        mock_fetch_tournament_by_id.return_value = {
            "name": "Test Tournament",
            "startAt": new_start,
            "endAt": new_end,
            "countryCode": "JP",
            "city": "Chiba",
            "lat": None,
            "lng": None,
            "venueName": None,
            "timezone": "Asia/Tokyo",
            "postalCode": None,
            "venueAddress": None,
            "mapsPlaceId": None,
            "url": "https://example.com",
        }
        mock_fetch_event_ids.return_value = [(10, "Singles", False, "COMPLETED", 1)]
        mock_download_standings.return_value = ([], [], {})

        with tempfile.TemporaryDirectory() as tmpdir:
            old_event_dir = get_event_directory(tmpdir, "JP", "2025", "08", "16", "Test Tournament", "Singles")
            os.makedirs(old_event_dir, exist_ok=True)
            with open(os.path.join(old_event_dir, "marker.json"), "w", encoding="utf-8") as f:
                f.write("{}")

            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            with open(tournament_file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "tournament_id": 1,
                        "name": "Test Tournament",
                        "events": [{"event_id": 10, "event_name": "Singles", "path": old_event_dir}],
                        "version": "1.0",
                    },
                    f,
                )
                f.write("\n")

            new_event_dir = get_event_directory(tmpdir, "JP", "2026", "02", "07", "Test Tournament", "Singles")
            os.makedirs(new_event_dir, exist_ok=True)

            download_by_ids(
                [1],
                "1386",
                "JP",
                f"{tmpdir}",
                f"{tmpdir}/done.csv",
                f"{tmpdir}/users.jsonl",
                tournament_file_path,
            )

            self.assertFalse(os.path.isdir(old_event_dir))
            self.assertTrue(os.path.isfile(os.path.join(new_event_dir, "attr.json")))

            updated = read_tournaments_jsonl(tournament_file_path)
            self.assertEqual(updated[1]["events"][0]["path"], new_event_dir)

    @patch("scripts.fetch.download.read_set", return_value=set())
    @patch("scripts.fetch.download.read_users_jsonl", return_value={})
    @patch("scripts.fetch.download.fetch_tournament_by_id")
    @patch("scripts.fetch.download.fetch_event_ids_from_tournament")
    @patch("scripts.fetch.download.download_standings")
    def test_download_by_ids_records_event_path_before_fetch_even_if_standings_fails(
        self,
        mock_standings,
        mock_fetch_event_ids,
        mock_fetch_tournament_by_id,
        _mock_read_users,
        _mock_read_set,
    ):
        # 004-fix-duplicate-events / 867504のケースで判明した通り、大規模イベント処理が
        # 途中で失敗しても event_id とパスの対応関係だけは tournaments.jsonl に残るように
        # なっていることを download_by_ids() 経由でも確認する。
        mock_fetch_tournament_by_id.return_value = {
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
        mock_fetch_event_ids.return_value = [(10, "Singles", False, "COMPLETED", 1)]
        mock_standings.side_effect = FetchError("standings query failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            download_by_ids(
                [1],
                "1386",
                "JP",
                f"{tmpdir}",
                f"{tmpdir}/done.csv",
                f"{tmpdir}/users.jsonl",
                tournament_file_path,
            )

            updated = read_tournaments_jsonl(tournament_file_path)

        self.assertEqual(len(updated[1]["events"]), 1)
        self.assertEqual(updated[1]["events"][0]["event_id"], 10)
        event_dir = updated[1]["events"][0]["path"]
        self.assertFalse(os.path.isfile(os.path.join(event_dir, "attr.json")))

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
        mock_fetch_event_ids.return_value = [(10, "Singles", False, "COMPLETED", 1)]
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

    @patch("scripts.fetch.download.read_set", return_value=set())
    @patch("scripts.fetch.download.read_users_jsonl", return_value={})
    @patch("scripts.fetch.download.fetch_latest_tournaments_by_game")
    @patch("scripts.fetch.download.fetch_event_ids_from_tournament")
    @patch("scripts.fetch.download.download_all_set")
    @patch("scripts.fetch.download.download_standings")
    @patch("scripts.fetch.download.download_seeds")
    @patch("scripts.fetch.download.extend_user_info")
    def test_download_all_tournaments_records_event_path_before_fetch_even_if_later_step_fails(
        self,
        _mock_extend_user_info,
        _mock_download_seeds,
        mock_download_standings,
        mock_download_all_set,
        mock_fetch_event_ids,
        mock_fetch_tournaments,
        _mock_read_users,
        _mock_read_set,
    ):
        # 大規模イベント処理(matches取得)が失敗しても、event_id と保存先パスの対応関係
        # 自体は tournaments.jsonl に記録され続けることを確認する(取得処理を始める前に
        # 記録しているため)。
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
        mock_fetch_event_ids.return_value = [(10, "Singles", False, "COMPLETED", 1)]
        mock_download_standings.return_value = ([], [], {})
        mock_download_all_set.side_effect = MaxPagesExceededError(total_pages=999, max_pages=10, per_page=10)

        with tempfile.TemporaryDirectory() as tmpdir:
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            download_all_tournaments(
                "1386",
                "JP",
                datetime(2024, 5, 4, 23, 59, 59),
                datetime(2024, 5, 4, 0, 0, 0),
                f"{tmpdir}",
                f"{tmpdir}/done.csv",
                f"{tmpdir}/users.jsonl",
                tournament_file_path,
            )

            updated = read_tournaments_jsonl(tournament_file_path)

        self.assertEqual(len(updated[1]["events"]), 1)
        self.assertEqual(updated[1]["events"][0]["event_id"], 10)
        event_dir = updated[1]["events"][0]["path"]
        self.assertFalse(os.path.isfile(os.path.join(event_dir, "attr.json")))

    @patch("scripts.fetch.download.read_set", return_value=set())
    @patch("scripts.fetch.download.read_users_jsonl", return_value={})
    @patch("scripts.fetch.download.fetch_latest_tournaments_by_game")
    @patch("scripts.fetch.download.fetch_event_ids_from_tournament")
    @patch("scripts.fetch.download.download_all_set")
    @patch("scripts.fetch.download.download_standings")
    @patch("scripts.fetch.download.download_seeds")
    @patch("scripts.fetch.download.extend_user_info")
    def test_download_all_tournaments_writes_skip_report_after_reaching_finish_date(
        self,
        _mock_extend_user_info,
        _mock_download_seeds,
        mock_download_standings,
        mock_download_all_set,
        mock_fetch_event_ids,
        mock_fetch_tournaments,
        _mock_read_users,
        _mock_read_set,
    ):
        # 走査が finish_date に達して打ち切られた回でも、その前に記録された
        # skipped_events (大規模イベントのスキップ報告) が失われないことを確認する
        # 回帰テスト。以前は finish_date 到達時に関数が早期 return しており、末尾の
        # skip_report_path 書き出し処理に到達できていなかった。
        mock_fetch_tournaments.return_value = (
            [
                {
                    "id": 1,
                    "name": "Large Tournament",
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
                },
                {
                    "id": 2,
                    "name": "Older Tournament",
                    "startAt": 1600000000,
                    "endAt": 1600003600,
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
                },
            ],
            1,
        )
        mock_fetch_event_ids.return_value = [(10, "Singles", False, "COMPLETED", 1)]
        mock_download_standings.return_value = ([], [], {})
        mock_download_all_set.side_effect = MaxPagesExceededError(total_pages=999, max_pages=10, per_page=10)

        with tempfile.TemporaryDirectory() as tmpdir:
            tournament_file_path = f"{tmpdir}/tournaments.jsonl"
            skip_report_path = f"{tmpdir}/skipped_events.json"
            download_all_tournaments(
                "1386",
                "JP",
                datetime(2024, 5, 4, 23, 59, 59),
                datetime(2024, 5, 4, 0, 0, 0),
                f"{tmpdir}",
                f"{tmpdir}/done.csv",
                f"{tmpdir}/users.jsonl",
                tournament_file_path,
                max_pages=10,
                skip_report_path=skip_report_path,
            )

            mock_fetch_event_ids.assert_called_once()

            self.assertTrue(os.path.isfile(skip_report_path))
            skipped = read_json(skip_report_path)
            self.assertEqual(len(skipped), 1)
            self.assertEqual(skipped[0]["tournament_id"], 1)
            self.assertEqual(skipped[0]["event_id"], 10)


if __name__ == "__main__":
    unittest.main()
