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

    def test_exit_overnight_portal_beats_earlier_evening_card(self):
        """Πραγματική 00:33 (επόμενη μέρα) κερδίζει κάρτα 23:59 ίδιας βάρδιας."""
        card = {"time": "23:59", "protocol": "ΚΕ363107690", "previous_events": []}
        display, meta, src = _merge_portal_and_card_punch_time(
            portal_time="00:33",
            portal_protocol="ΚΕ363131156",
            card_entry=card,
            punch_kind="out",
        )
        self.assertEqual(display, "00:33")
        self.assertIsNone(src)
        self.assertTrue(meta.get("superseded_by_portal"))
        self.assertEqual(meta.get("portal_protocol"), "ΚΕ363131156")
        self.assertNotIn("corrected_previous_time", meta)

    def test_exit_card_later_marks_portal_as_corrected(self):
        card = {"time": "20:30", "protocol": "ΚΕ1", "previous_events": []}
        display, meta, src = _merge_portal_and_card_punch_time(
            portal_time="19:00",
            portal_protocol="ΚΕ0",
            card_entry=card,
            punch_kind="out",
        )
        self.assertEqual(display, "20:30")
        self.assertEqual(src, "card_event_correction")
        self.assertEqual(meta.get("corrected_previous_time"), "19:00")
        self.assertEqual(meta.get("corrected_previous_protocol"), "ΚΕ0")

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

    def test_entry_empty_portal_uses_card_time(self):
        card = {"time": "14:05", "protocol": "ΚΕ397441455", "previous_events": []}
        display, meta, src = _merge_portal_and_card_punch_time(
            portal_time="",
            card_entry=card,
            punch_kind="in",
        )
        self.assertEqual(display, "14:05")
        self.assertEqual(src, "card_event")

    def test_drop_same_day_leftover_exit_when_complete_pair_exists(self):
        from app.repo_work_log import drop_same_day_leftover_exit_rows

        rows = [
            {
                "employee_afm": "201980886",
                "work_date": "26/09/2026",
                "hour_from": "12:50",
                "hour_to": "22:01",
            },
            {
                "employee_afm": "201980886",
                "work_date": "26/09/2026",
                "hour_from": "",
                "hour_to": "01:04",
            },
            {
                "employee_afm": "201980886",
                "work_date": "14/09/2026",
                "hour_from": "",
                "hour_to": "23:04",
            },
        ]
        out = drop_same_day_leftover_exit_rows(rows)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["hour_from"], "12:50")
        self.assertEqual(out[1]["work_date"], "14/09/2026")

    def test_open_punches_count_skips_card_closed_gaps(self):
        from app.repo_work_log import _pending_incomplete_counts

        rows = [
            {
                "employee_afm": "201980886",
                "work_date": "09/09/2026",
                "hour_from": "",
                "hour_to": "23:02",
            },
            {
                "employee_afm": "201980886",
                "work_date": "14/09/2026",
                "hour_from": "",
                "hour_to": "23:04",
            },
            {
                "employee_afm": "201980886",
                "work_date": "26/09/2026",
                "hour_from": "",
                "hour_to": "01:04",
            },
        ]
        cards = {
            ("201980886", "09/09/2026"): {
                "types": {"0"},
                "check_in": {"time": "12:58"},
                "check_out": None,
            },
            ("201980886", "14/09/2026"): {
                "types": {"0"},
                "check_in": {"time": "14:05"},
                "check_out": None,
            },
        }
        self.assertEqual(_pending_incomplete_counts(rows, cards), {"201980886": 1})


if __name__ == "__main__":
    unittest.main()
