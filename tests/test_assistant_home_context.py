import json
import unittest
from unittest.mock import patch

from app.assistant_home_context import (
    build_today_home_context,
    compact_home_employee_row,
)
from app.telegram_assistant_service import parse_command


class AssistantHomeContextTests(unittest.TestCase):
    def test_compact_home_employee_row_keeps_schedule_card_and_status(self):
        row = compact_home_employee_row({
            "employee_afm": "111222333",
            "eponymo": "TEST",
            "onoma": "ONE",
            "status": "at_work",
            "status_label": "Σε εργασία",
            "schedule": {
                "hour_from": "09:00",
                "hour_to": "15:30",
                "shift_type": "ΕΡΓΑΣΙΑ",
                "intervals": [{"hour_from": "09:00", "hour_to": "15:30"}],
            },
            "card": {
                "check_in": "09:05",
                "check_out": "—",
                "has_check_in": True,
                "has_check_out": False,
            },
        })
        self.assertEqual(row["afm"], "111222333")
        self.assertEqual(row["name"], "TEST ONE")
        self.assertEqual(row["schedule_to"], "15:30")
        self.assertEqual(row["card_in"], "09:05")
        self.assertNotIn("card_out", row)

    def test_build_today_home_context_includes_today_and_yesterday_open(self):
        contexts = [{
            "store_id": 4,
            "store_name": "ERATO",
            "employer_afm": "123456789",
            "branch_aa": "0",
        }]
        today_report = {
            "summary": {"total": 1, "at_work": 1},
            "rows": [{
                "employee_afm": "111222333",
                "eponymo": "TEST",
                "onoma": "ONE",
                "status": "at_work",
                "status_label": "Σε εργασία",
                "schedule": {
                    "hour_from": "09:00",
                    "hour_to": "15:30",
                    "intervals": [{"hour_from": "09:00", "hour_to": "15:30"}],
                },
                "card": {
                    "check_in": "09:05",
                    "has_check_in": True,
                    "has_check_out": False,
                },
            }],
        }
        yesterday_report = {
            "summary": {"total": 2, "at_work": 1, "completed": 1},
            "rows": [
                {
                    "employee_afm": "111222333",
                    "eponymo": "OPEN",
                    "onoma": "YDAY",
                    "status": "needs_checkout",
                    "schedule": {"hour_from": "16:00", "hour_to": "01:00"},
                    "card": {"check_in": "16:05", "has_check_in": True, "has_check_out": False},
                },
                {
                    "employee_afm": "999888777",
                    "eponymo": "CLOSED",
                    "onoma": "YDAY",
                    "status": "completed",
                    "schedule": {"hour_from": "10:00", "hour_to": "18:00"},
                    "card": {
                        "check_in": "10:00",
                        "check_out": "18:00",
                        "has_check_in": True,
                        "has_check_out": True,
                    },
                },
            ],
        }
        calls: list[str] = []

        def fake_report(_employer, _branch, date_iso=None):
            calls.append(str(date_iso))
            return today_report if len(calls) == 1 else yesterday_report

        with patch("app.assistant_home_context.build_card_status_report", side_effect=fake_report):
            snapshot = build_today_home_context(contexts)
        self.assertEqual(len(calls), 2)
        self.assertEqual(snapshot["scope"], "today_and_yesterday")
        self.assertEqual(snapshot["date"], calls[0])
        self.assertEqual(snapshot["yesterday_date"], calls[1])
        self.assertEqual(len(snapshot["stores"]), 1)
        self.assertEqual(snapshot["stores"][0]["employees"][0]["schedule_to"], "15:30")
        y_emps = snapshot["yesterday"]["stores"][0]["employees"]
        self.assertEqual(len(y_emps), 1)
        self.assertEqual(y_emps[0]["afm"], "111222333")
        self.assertEqual(snapshot["yesterday"]["stores"][0]["open_count"], 1)

    def test_parse_command_includes_today_home_when_group_query(self):
        contexts = [{
            "store_id": 4,
            "store_name": "ERATO",
            "employer_afm": "123456789",
            "branch_aa": "0",
        }]
        employees = [{"store_id": 4, "afm": "111222333", "name": "TEST ONE"}]
        today_home = {
            "date": "2026-08-18",
            "scope": "today_only",
            "stores": [{
                "store_id": 4,
                "name": "ERATO",
                "employees": [{
                    "afm": "111222333",
                    "name": "TEST ONE",
                    "status": "at_work",
                    "schedule_to": "15:30",
                    "card_in": "09:05",
                }],
            }],
        }
        captured: dict = {}

        def fake_post(url, **kwargs):
            captured["prompt"] = json.loads(kwargs["json"]["contents"][0]["parts"][0]["text"])
            response = unittest.mock.MagicMock(ok=True, status_code=200)
            response.json.return_value = {
                "modelVersion": "gemini-test",
                "candidates": [{"content": {"parts": [{"text": json.dumps({
                    "commands": [{
                        "intent": "card_check_out_now",
                        "store_id": 4,
                        "employee_afms": ["111222333"],
                        "employee_references": ["TEST ONE"],
                        "date": "2026-08-18",
                        "confidence": 0.99,
                    }],
                }, ensure_ascii=False)}]}}],
                "usageMetadata": {"totalTokenCount": 10},
            }
            return response

        with patch("app.telegram_assistant_service.Config.GEMINI_API_KEY", "test"), \
             patch("app.telegram_assistant_service._employee_catalog", return_value=employees), \
             patch("app.telegram_assistant_service.build_today_home_context", return_value=today_home) as build_home, \
             patch("app.telegram_assistant_service.requests.post", side_effect=fake_post):
            parsed, _, _ = parse_command(
                text="κλείσε τώρα όσους τελειώνουν στις 15:30",
                contexts=contexts,
            )
        build_home.assert_called_once()
        self.assertIn("today_home", captured["prompt"])
        self.assertEqual(captured["prompt"]["today_home"]["stores"][0]["employees"][0]["schedule_to"], "15:30")
        guide = " ".join(captured["prompt"]["guide"])
        self.assertIn("greeklish", guide.casefold())
        self.assertIn("today_info", guide)
        intent = parsed.get("intent") or (parsed.get("commands") or [{}])[0].get("intent")
        self.assertEqual(intent, "card_check_out_now")

    def test_parse_command_always_includes_today_home(self):
        contexts = [{
            "store_id": 4,
            "store_name": "ERATO",
            "employer_afm": "123456789",
            "branch_aa": "0",
        }]
        employees = [{"store_id": 4, "afm": "111222333", "name": "HOXHA ARBEN"}]
        today_home = {
            "date": "2026-08-18",
            "scope": "today_only",
            "stores": [{"store_id": 4, "name": "ERATO", "employees": []}],
        }
        captured: dict = {}

        def fake_post(url, **kwargs):
            captured["prompt"] = json.loads(kwargs["json"]["contents"][0]["parts"][0]["text"])
            response = unittest.mock.MagicMock(ok=True, status_code=200)
            response.json.return_value = {
                "modelVersion": "gemini-test",
                "candidates": [{"content": {"parts": [{"text": json.dumps({
                    "commands": [{
                        "intent": "card_check_in_now",
                        "store_id": 4,
                        "employee_afms": ["111222333"],
                        "employee_references": ["HOXHA"],
                        "date": "2026-08-18",
                        "confidence": 0.99,
                    }],
                }, ensure_ascii=False)}]}}],
                "usageMetadata": {"totalTokenCount": 10},
            }
            return response

        with patch("app.telegram_assistant_service.Config.GEMINI_API_KEY", "test"), \
             patch("app.telegram_assistant_service._employee_catalog", return_value=employees), \
             patch("app.telegram_assistant_service.build_today_home_context", return_value=today_home) as build_home, \
             patch("app.telegram_assistant_service.requests.post", side_effect=fake_post):
            parse_command(text="άνοιξε την κάρτα του HOXHA", contexts=contexts)
        build_home.assert_called_once()
        self.assertIn("today_home", captured["prompt"])
        guide = " ".join(captured["prompt"]["guide"])
        self.assertIn("today_home είναι ΠΑΝΤΑ", guide)


if __name__ == "__main__":
    unittest.main()
