import unittest

from app.public_urls import effective_public_base_url, ui_public_url, ui_relative_path
from config import Config


class PublicUrlsTests(unittest.TestCase):
    def test_relative_path_keeps_same_origin(self):
        self.assertEqual(
            ui_relative_path("/ui/today-hit", token="abc"),
            "/ui/today-hit?t=abc",
        )

    def test_public_url_uses_effective_base(self):
        old = Config.PUBLIC_BASE_URL
        old_debug = Config.FLASK_DEBUG
        Config.PUBLIC_BASE_URL = "http://localhost:5051"
        Config.FLASK_DEBUG = False
        try:
            url = ui_public_url("/ui/today-hit", token="x")
            self.assertTrue(url.startswith("https://erganios.gr/ui/today-hit"))
        finally:
            Config.PUBLIC_BASE_URL = old
            Config.FLASK_DEBUG = old_debug

    def test_effective_base_honors_debug_localhost(self):
        old = Config.PUBLIC_BASE_URL
        old_debug = Config.FLASK_DEBUG
        Config.PUBLIC_BASE_URL = "http://localhost:5051"
        Config.FLASK_DEBUG = True
        try:
            self.assertEqual(
                effective_public_base_url(),
                "http://localhost:5051",
            )
        finally:
            Config.PUBLIC_BASE_URL = old
            Config.FLASK_DEBUG = old_debug


if __name__ == "__main__":
    unittest.main()
