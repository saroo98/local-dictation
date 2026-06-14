import json
import tempfile
import unittest
from pathlib import Path

import settings


class FakeEntry:
    def __init__(self, text, display_time):
        self.text = text
        self.display_time = display_time


class MergeAndValidateTests(unittest.TestCase):
    def test_merge_fills_defaults_for_missing_keys(self):
        merged = settings.merge_settings(settings.DEFAULT_SETTINGS, {"language": "Arabic"})
        self.assertEqual(merged["language"], "Arabic")
        self.assertEqual(merged["model"], settings.DEFAULT_SETTINGS["model"])

    def test_validate_rejects_unknown_choices(self):
        merged = settings.merge_settings(settings.DEFAULT_SETTINGS, {"model": "Nope"})
        self.assertEqual(merged["model"], settings.DEFAULT_SETTINGS["model"])

    def test_opacity_is_clamped(self):
        self.assertEqual(settings.validate_settings({"opacity": 5})["opacity"], settings.config.OPACITY_MIN)
        self.assertEqual(settings.validate_settings({"opacity": 500})["opacity"], settings.config.OPACITY_MAX)

    def test_bubble_position_must_be_two_ints(self):
        self.assertEqual(settings.validate_settings({"bubble_position": [10, 20]})["bubble_position"], [10, 20])
        self.assertIsNone(settings.validate_settings({"bubble_position": "x"})["bubble_position"])


class MappingTests(unittest.TestCase):
    def test_language_codes(self):
        self.assertEqual(settings.language_to_whisper_code("English (US)"), "en")
        self.assertIsNone(settings.language_to_whisper_code("Auto Detect"))
        self.assertIsNone(settings.language_to_whisper_code("Kurdish"))
        self.assertEqual(settings.language_to_whisper_code("Persian"), "fa")
        self.assertEqual(settings.language_to_whisper_code("Arabic"), "ar")

    def test_model_tiers(self):
        self.assertEqual(settings.model_tier_to_name("Fast"), "small")
        self.assertEqual(settings.model_tier_to_name("Balanced"), "large-v3-turbo")
        self.assertEqual(settings.model_tier_to_name("High Accuracy"), "large-v3")

    def test_palette_for_light_and_dark(self):
        self.assertEqual(settings.palette_for("Light Mode"), settings.LIGHT_PALETTE)
        self.assertEqual(settings.palette_for("Dark Mode"), settings.DARK_PALETTE)


class RoundTripTests(unittest.TestCase):
    def test_save_then_load_roundtrips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            settings.save_settings({"language": "Persian", "opacity": 80}, path)
            loaded = settings.load_settings(path)
            self.assertEqual(loaded["language"], "Persian")
            self.assertEqual(loaded["opacity"], 80)

    def test_load_missing_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            loaded = settings.load_settings(Path(temp_dir) / "absent.json")
            self.assertEqual(loaded, settings.DEFAULT_SETTINGS)


class ExportTests(unittest.TestCase):
    def test_plain_export_includes_time_and_text(self):
        out = settings.format_history_export([FakeEntry("hello", "10:35 AM")], "Plain Text")
        self.assertIn("[10:35 AM]", out)
        self.assertIn("hello", out)

    def test_markdown_export_uses_headings(self):
        out = settings.format_history_export([FakeEntry("hello", "10:35 AM")], "Markdown (.md)")
        self.assertIn("## 10:35 AM", out)
        self.assertTrue(settings.export_extension("Markdown (.md)") == ".md")

    def test_empty_history_exports_empty_string(self):
        self.assertEqual(settings.format_history_export([], "Plain Text"), "")


if __name__ == "__main__":
    unittest.main()
