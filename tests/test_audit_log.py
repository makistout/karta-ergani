import unittest
from unittest.mock import patch

from app.audit_log import _safe_payload, list_audit_events


class AuditLogTests(unittest.TestCase):
    def test_safe_payload_redacts_sensitive_keys_recursively(self):
        payload = {
            "username": "admin",
            "password": "secret",
            "nested": {
                "accessToken": "abc",
                "notify_pin": "1234",
                "ok": True,
            },
            "items": [
                {"api_key": "key", "name": "row"},
            ],
        }

        safe = _safe_payload(payload)

        self.assertEqual(safe["username"], "admin")
        self.assertEqual(safe["password"], "***")
        self.assertEqual(safe["nested"]["accessToken"], "***")
        self.assertEqual(safe["nested"]["notify_pin"], "***")
        self.assertEqual(safe["nested"]["ok"], True)
        self.assertEqual(safe["items"][0]["api_key"], "***")
        self.assertEqual(safe["items"][0]["name"], "row")

    def test_auth_kind_filters_auth_actions(self):
        class FakeCursor:
            description = []
            sql = ""

            def execute(self, sql, params):
                self.sql = sql
                self.params = params

            def fetchall(self):
                return []

        class FakeContext:
            cur = FakeCursor()

            def __enter__(self):
                return self.cur

            def __exit__(self, exc_type, exc, tb):
                return False

        ctx = FakeContext()

        with patch("app.audit_log.cursor", return_value=ctx):
            result = list_audit_events(kind="auth", limit=10, before_id=100)

        self.assertEqual(result["rows"], [])
        self.assertFalse(result["has_more"])
        self.assertIn("action LIKE N'auth.%'", ctx.cur.sql)
        self.assertIn("SELECT TOP (?)", ctx.cur.sql)
        self.assertEqual(ctx.cur.params[0], 11)  # limit+1
        self.assertEqual(ctx.cur.params[-1], 100)  # before_id

    def test_scanner_punches_kind_filters_channel(self):
        class FakeCursor:
            description = []
            sql = ""

            def execute(self, sql, params):
                self.sql = sql
                self.params = params

            def fetchall(self):
                return []

        class FakeContext:
            cur = FakeCursor()

            def __enter__(self):
                return self.cur

            def __exit__(self, exc_type, exc, tb):
                return False

        ctx = FakeContext()

        with patch("app.audit_log.cursor", return_value=ctx):
            list_audit_events(kind="scanner_punches", limit=10)

        self.assertIn("action = N'work_card_punch_submit'", ctx.cur.sql)
        self.assertIn('%"submission_channel":"scanner"%', ctx.cur.sql)
        self.assertIn("details_json LIKE", ctx.cur.sql)


if __name__ == "__main__":
    unittest.main()
