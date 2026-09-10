from __future__ import annotations

from pathlib import Path
import unittest


BOT_SOURCE = Path(__file__).parents[1].joinpath("app", "bot.py").read_text()


class BotUiTests(unittest.TestCase):
    def test_web_app_button_is_available(self) -> None:
        self.assertIn("✨ فتح واجهة RABET", BOT_SOURCE)
        self.assertIn("web_app=WebAppInfo(url=self.settings.web_app_url)", BOT_SOURCE)
        self.assertIn("handle_web_app_data", BOT_SOURCE)

    def test_credits_include_owner_contact(self) -> None:
        self.assertIn("Abdulrahman Alzahrani", BOT_SOURCE)
        self.assertIn("333.alsadi@gmail.com", BOT_SOURCE)
