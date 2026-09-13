from pathlib import Path
import tempfile
import unittest

from core.remote import DESKTOP_ACTIONS, SYSTEM_MEDIA_ACTIONS
from core.settings import Settings
from core.windows_media import parse_lrc


class RemoteCoreTests(unittest.TestCase):
    def test_parse_lrc_multiple_timestamps_and_fraction_widths(self):
        lines = parse_lrc("[00:01.50][00:03.250]Hello\n[01:02]World")
        self.assertEqual([item["time"] for item in lines], [1.5, 3.25, 62.0])
        self.assertEqual([item["text"] for item in lines], ["Hello", "Hello", "World"])

    def test_remote_settings_are_migrated_for_old_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"theme":"自定义"}', encoding="utf-8")
            settings = Settings(path)
            self.assertTrue(settings.data["remote"]["enabled"])
            self.assertEqual(settings.data["remote"]["port"], 8765)
            self.assertEqual(settings.data["remote"]["pin"], "")

    def test_mobile_surface_has_no_game_commands(self):
        actions = DESKTOP_ACTIONS | SYSTEM_MEDIA_ACTIONS
        for forbidden in ("snake", "mole", "rhythm", "waterfall", "maimai", "game"):
            self.assertFalse(any(forbidden in action.casefold() for action in actions))

    def test_media_actions_are_explicitly_allowlisted(self):
        self.assertIn("system_media.play_pause", SYSTEM_MEDIA_ACTIONS)
        self.assertIn("system_media.seek", SYSTEM_MEDIA_ACTIONS)
        self.assertIn("system_media.output", SYSTEM_MEDIA_ACTIONS)
        self.assertNotIn("system_media.command", SYSTEM_MEDIA_ACTIONS)


if __name__ == "__main__":
    unittest.main()
