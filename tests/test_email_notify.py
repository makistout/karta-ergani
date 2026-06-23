import unittest

from app.email_notify import build_notification_email


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


if __name__ == "__main__":
    unittest.main()
