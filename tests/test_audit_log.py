import unittest

from app.audit_log import _safe_payload


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


if __name__ == "__main__":
    unittest.main()
