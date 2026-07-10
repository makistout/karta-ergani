import unittest
from unittest.mock import patch

from app.email_notify import build_notification_email
from app.user_email_verification import (
    NEW_MEMBER_EMAIL_BCC,
    build_verification_email,
    send_verification_email,
)


class EmailNotifyTests(unittest.TestCase):
    def test_build_notification_email_escapes_content_and_keeps_action_url(self):
        text_body, html_body = build_notification_email(
            title="Ειδοποίηση <x>",
            preheader="Προεπισκόπηση",
            store_name="Κατάστημα & Co",
            employee_name="Παπαδόπουλος <Νίκος>",
            employee_afm="123456789",
            work_date="23/06/2026",
            problem="Χρειάζεται <ενέργεια> & έλεγχος.",
            details=[("Ώρα από", "09:00")],
            action_url="https://example.test/ui/telegram-hit?t=abc",
            action_label="Άνοιγμα",
        )

        self.assertIn("Ειδοποίηση <x>", text_body)
        self.assertIn("https://example.test/ui/telegram-hit?t=abc", text_body)
        self.assertIn("Ειδοποίηση &lt;x&gt;", html_body)
        self.assertIn("Κατάστημα &amp; Co", html_body)
        self.assertIn("Παπαδόπουλος &lt;Νίκος&gt;", html_body)
        self.assertIn('href="https://example.test/ui/telegram-hit?t=abc"', html_body)
        self.assertNotIn("Χρειάζεται <ενέργεια>", html_body)

    @patch("app.user_email_verification.send_email_message")
    def test_send_verification_email_bccs_info(self, send_email_message):
        send_email_message.return_value = {"ok": True, "to": "new@example.gr"}

        send_verification_email(
            email="new@example.gr",
            username="new-user",
            full_name="New User",
            token="tok",
        )

        send_email_message.assert_called_once()
        assert send_email_message.call_args.kwargs["bcc"] == NEW_MEMBER_EMAIL_BCC
        assert NEW_MEMBER_EMAIL_BCC == "info@erganios.gr"

    def test_verification_email_uses_full_name_not_username(self):
        text, html_body = build_verification_email(
            username="giorgos",
            full_name="Γιώργος Τσαγκαράκης",
            url="https://erganios.gr/ui/verify-email?t=abc",
        )
        assert "Γιώργος Τσαγκαράκης" in text
        assert "giorgos" not in text
        assert "Roboto" in html_body
        assert "Γιώργος Τσαγκαράκης" in html_body

    def test_verification_email_without_full_name_uses_neutral_greeting(self):
        text, _html = build_verification_email(
            username="giorgos",
            full_name=None,
            url="https://erganios.gr/ui/verify-email?t=abc",
        )
        assert "Γεια σας χρήστη," in text
        assert "giorgos" not in text


if __name__ == "__main__":
    unittest.main()
