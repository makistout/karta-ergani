"""Tests για σύγχωνευση πραγματικής με δηλώσεις κάρτας."""

import unittest

from app.repo_work_log import _merge_portal_and_card_punch_time


class WorkLogCardMergeTests(unittest.TestCase):
    def test_exit_portal_later_keeps_portal_without_correction_badge(self):
        card = {"time": "19:33", "protocol": "ΚΕ328639150", "previous_events": []}
        display, meta, src = _merge_portal_and_card_punch_time(
            portal_time="20:41",
            card_entry=card,
            punch_kind="out",
        )
        self.assertEqual(display, "20:41")
        self.assertIsNone(src)
        self.assertTrue(meta.get("superseded_by_portal"))
        self.assertNotIn("corrected_previous_time", meta)

    def test_exit_card_later_marks_portal_as_corrected(self):
        card = {"time": "20:30", "protocol": "ΚΕ1", "previous_events": []}
        display, meta, src = _merge_portal_and_card_punch_time(
            portal_time="19:00",
            card_entry=card,
            punch_kind="out",
        )
        self.assertEqual(display, "20:30")
        self.assertEqual(src, "card_event_correction")
        self.assertEqual(meta.get("corrected_previous_time"), "19:00")

    def test_exit_card_chain_correction_unchanged(self):
        card = {
            "time": "20:30",
            "protocol": "ΚΕ2",
            "previous_events": [{"time": "19:00", "protocol": "ΚΕ1"}],
        }
        display, meta, src = _merge_portal_and_card_punch_time(
            portal_time="19:00",
            card_entry=card,
            punch_kind="out",
        )
        self.assertEqual(display, "20:30")
        self.assertEqual(src, "card_event_correction")
        self.assertEqual(len(meta.get("previous_events") or []), 1)

    def test_entry_card_later_marks_portal_as_corrected(self):
        card = {"time": "12:10", "protocol": "ΚΕ1", "previous_events": []}
        display, meta, src = _merge_portal_and_card_punch_time(
            portal_time="11:56",
            card_entry=card,
            punch_kind="in",
        )
        self.assertEqual(display, "12:10")
        self.assertEqual(src, "card_event_correction")
        self.assertEqual(meta.get("corrected_previous_time"), "11:56")

    def test_entry_card_earlier_keeps_card_without_correction(self):
        card = {"time": "11:56", "protocol": "ΚΕ1", "previous_events": []}
        display, meta, src = _merge_portal_and_card_punch_time(
            portal_time="12:00",
            card_entry=card,
            punch_kind="in",
        )
        self.assertEqual(display, "11:56")
        self.assertEqual(src, "card_event")
        self.assertNotIn("corrected_previous_time", meta)


if __name__ == "__main__":
    unittest.main()
