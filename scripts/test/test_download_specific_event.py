import os
import tempfile
import unittest
from unittest.mock import patch

from scripts import labeling
from scripts.fetch.download_specific_event import write_event_attributes
from scripts.utils import EVENT_DATA_VERSION, read_json


class WriteEventAttributesTests(unittest.TestCase):
    """T011/T024: download_specific_event.py の独自実装への回帰確認
    (scripts/fetch/download.py の同名テストと同等のケース)。"""

    def _place(self):
        return {
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

    def _with_label_ruleset(self, ruleset):
        labeling._load_compiled_ruleset.cache_clear()
        return patch.object(labeling, "load_label_ruleset", return_value=ruleset)

    def test_write_event_attributes_includes_version_and_guest_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            write_event_attributes(
                10, 999, "Event", "Tournament", 1710001000, self._place(),
                "https://example.com", {}, True, tmpdir,
                guest_entrant_count=3,
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
        self.assertEqual(attr["event_data_version"], EVENT_DATA_VERSION)
        self.assertEqual(attr["guest_entrant_count"], 3)

    def test_write_event_attributes_sets_matching_label_and_version(self):
        ruleset = {
            "label_version": 4,
            "matches": [{"label": "registration_restricted", "tournament_name_match": "制限"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir, self._with_label_ruleset(ruleset):
            write_event_attributes(
                10, 999, "Singles", "第1回制限大会", 1710001000, self._place(),
                "https://example.com", {}, True, tmpdir,
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
        labeling._load_compiled_ruleset.cache_clear()
        self.assertEqual(attr["labels"], {"registration_restricted": True})
        self.assertEqual(attr["label_version"], 4)

    def test_write_event_attributes_and_condition_requires_both(self):
        ruleset = {
            "label_version": 4,
            "matches": [
                {"label": "casual", "tournament_name_match": "スマパ", "event_name_match": "カジュアル"}
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir, self._with_label_ruleset(ruleset):
            write_event_attributes(
                10, 999, "Singles", "スマパ", 1710001000, self._place(),
                "https://example.com", {}, True, tmpdir,
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
        labeling._load_compiled_ruleset.cache_clear()
        self.assertNotIn("casual", attr["labels"])

    def test_write_event_attributes_no_match_still_records_label_version(self):
        ruleset = {
            "label_version": 4,
            "matches": [{"label": "registration_restricted", "tournament_name_match": "制限"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir, self._with_label_ruleset(ruleset):
            write_event_attributes(
                10, 999, "Singles", "通常大会", 1710001000, self._place(),
                "https://example.com", {}, True, tmpdir,
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
        labeling._load_compiled_ruleset.cache_clear()
        self.assertNotIn("registration_restricted", attr["labels"])
        self.assertEqual(attr["label_version"], 4)

    def test_write_event_attributes_preserves_unmanaged_existing_labels(self):
        ruleset = {
            "label_version": 4,
            "matches": [{"label": "registration_restricted", "tournament_name_match": "制限"}],
        }
        existing_labels = {"registration_type": "full-open"}
        with tempfile.TemporaryDirectory() as tmpdir, self._with_label_ruleset(ruleset):
            write_event_attributes(
                10, 999, "Singles", "第1回制限大会", 1710001000, self._place(),
                "https://example.com", existing_labels, True, tmpdir,
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
        labeling._load_compiled_ruleset.cache_clear()
        self.assertEqual(
            attr["labels"], {"registration_type": "full-open", "registration_restricted": True}
        )

    def test_write_event_attributes_min_event_data_version_gate_skips_label_version(self):
        ruleset = {
            "label_version": 4,
            "min_event_data_version": EVENT_DATA_VERSION + 1,
            "matches": [{"label": "registration_restricted", "tournament_name_match": "制限"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir, self._with_label_ruleset(ruleset):
            write_event_attributes(
                10, 999, "Singles", "第1回制限大会", 1710001000, self._place(),
                "https://example.com", {"registration_type": "full-open"}, True, tmpdir,
            )
            attr = read_json(os.path.join(tmpdir, "attr.json"))
        labeling._load_compiled_ruleset.cache_clear()
        self.assertNotIn("label_version", attr)
        self.assertEqual(attr["labels"], {"registration_type": "full-open"})


if __name__ == "__main__":
    unittest.main()
