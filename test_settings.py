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
        self.assertEqual(settings.model_tier_to_name("Ultra Fast English"), "tiny.en")
        self.assertEqual(settings.model_tier_to_name("Compact Multilingual"), "base")
        self.assertEqual(settings.model_tier_to_name("Medium Quality"), "medium")

    def test_builtin_model_choices_keep_default_three_first(self):
        self.assertEqual(settings.MODEL_CHOICES[:3], ["Fast", "Balanced", "High Accuracy"])
        self.assertEqual(
            settings.MODEL_CHOICES[3:],
            ["Ultra Fast English", "Compact Multilingual", "Medium Quality"],
        )

    def test_model_choices_can_be_ordered_by_speed_or_accuracy(self):
        self.assertEqual(
            settings.model_choices(order="Speed"),
            [
                "Ultra Fast English",
                "Compact Multilingual",
                "Fast",
                "Medium Quality",
                "Balanced",
                "High Accuracy",
            ],
        )
        self.assertEqual(
            settings.model_choices(order="Accuracy"),
            [
                "High Accuracy",
                "Balanced",
                "Medium Quality",
                "Fast",
                "Compact Multilingual",
                "Ultra Fast English",
            ],
        )

    def test_model_dropdown_labels_include_model_name_and_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            options = settings.model_dropdown_options(
                order="Speed",
                cache_root=Path(temp_dir),
            )

        self.assertTrue(options[0].startswith("Ultra Fast English - tiny.en - 75 MB"))
        self.assertIn("Fast - small - 464 MB", options)
        self.assertTrue(options[-1].startswith("High Accuracy - large-v3 - 2.95 GB"))

    def test_model_choice_can_be_resolved_from_dropdown_label(self):
        label = "Fast - small - 464 MB"

        self.assertEqual(settings.model_choice_from_dropdown_label(label), "Fast")

    def test_model_order_setting_is_validated(self):
        values = settings.validate_settings({"model_order": "Accuracy"})
        self.assertEqual(values["model_order"], "Accuracy")

        values = settings.validate_settings({"model_order": "Newest"})
        self.assertEqual(values["model_order"], settings.DEFAULT_SETTINGS["model_order"])

    def test_model_details_include_repo_revision_and_local_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            repo_dir = cache_root / "models--Systran--faster-whisper-large-v3"
            snapshot = repo_dir / "snapshots" / "abc123"
            snapshot.mkdir(parents=True)
            (repo_dir / "refs").mkdir()
            (repo_dir / "refs" / "main").write_text("abc123", encoding="utf-8")
            (snapshot / "model.bin").write_bytes(b"x" * 1024)

            details = settings.model_tier_details("High Accuracy", cache_root=cache_root)

        self.assertEqual(details["tier"], "High Accuracy")
        self.assertEqual(details["model_name"], "large-v3")
        self.assertEqual(details["repo_id"], "Systran/faster-whisper-large-v3")
        self.assertEqual(details["revision"], "abc123")
        self.assertEqual(details["size_text"], "1 KB")
        self.assertTrue(details["available"])

    def test_missing_model_details_mark_tier_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            details = settings.model_tier_details("Fast", cache_root=Path(temp_dir))

        self.assertEqual(details["repo_id"], "Systran/faster-whisper-small")
        self.assertFalse(details["available"])
        self.assertEqual(details["size_text"], "not installed locally")

    def test_metadata_only_cache_does_not_mark_model_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            repo_dir = cache_root / "models--Systran--faster-whisper-base"
            repo_dir.mkdir(parents=True)
            (repo_dir / "refs").mkdir()
            (repo_dir / "refs" / "main").write_text("abc123", encoding="utf-8")
            (repo_dir / "blobs").mkdir()
            (repo_dir / "blobs" / "metadata-only").write_text("x", encoding="utf-8")

            details = settings.model_tier_details("Compact Multilingual", cache_root=cache_root)

        self.assertFalse(details["available"])
        self.assertEqual(details["size_text"], "not installed locally")

    def test_model_tier_summary_is_human_readable(self):
        summary = settings.model_tier_summary("Fast", cache_root=Path("Z:/definitely-missing"))

        self.assertIn("Fast", summary)
        self.assertIn("small", summary)
        self.assertIn("Systran/faster-whisper-small", summary)
        self.assertIn("not installed locally", summary)

    def test_custom_model_local_folder_is_accepted_when_ctranslate2_files_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir) / "local-model"
            model_dir.mkdir()
            for filename in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
                (model_dir / filename).write_text("x", encoding="utf-8")

            values = settings.validate_settings(
                {
                    "custom_models": [{"name": "Local Custom", "source": str(model_dir)}],
                    "model": "Local Custom",
                }
            )

        self.assertEqual(values["custom_models"], [{"name": "Local Custom", "source": str(model_dir)}])
        self.assertEqual(values["model"], "Local Custom")
        self.assertEqual(
            settings.model_tier_to_name("Local Custom", custom_models=values["custom_models"]),
            str(model_dir),
        )

    def test_custom_model_validation_rejects_duplicates_and_invalid_sources(self):
        values = settings.validate_settings(
            {
                "custom_models": [
                    {"name": "Duplicate", "source": "Systran/faster-whisper-base"},
                    {"name": "Duplicate", "source": "Systran/faster-whisper-medium"},
                    {"name": "Bad Source", "source": "not a valid local path"},
                ],
                "model": "Bad Source",
            }
        )

        self.assertEqual(values["custom_models"], [{"name": "Duplicate", "source": "Systran/faster-whisper-base"}])
        self.assertEqual(values["model"], settings.DEFAULT_SETTINGS["model"])

    def test_custom_hugging_face_repo_details_can_be_unavailable_until_downloaded(self):
        values = settings.validate_settings(
            {
                "custom_models": [
                    {"name": "Repo Custom", "source": "Systran/faster-whisper-base"},
                ],
                "model": "Repo Custom",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            details = settings.model_tier_details(
                "Repo Custom",
                cache_root=Path(temp_dir),
                custom_models=values["custom_models"],
            )

        self.assertEqual(details["repo_id"], "Systran/faster-whisper-base")
        self.assertFalse(details["available"])
        self.assertEqual(details["source_type"], "repo")

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
