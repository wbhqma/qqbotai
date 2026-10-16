import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dotenv import dotenv_values

from app.config import Settings
from configure import configure_pexels, main
from scripts.check_privacy import PRIVATE_FIELDS, inspect_text, local_private_values


class PexelsConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / ".env"
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.original = (
            '# keep comments and unrelated formatting\n'
            'LLM_API_KEY="test-model-key"\n'
            'VISION_API_KEY="test-vision-key"\n'
            'SERPAPI_API_KEY="test-search-key"\n'
            'PEXELS_API_KEY="test-old-key"\n'
            'CUSTOM_FIELD="keep spaces # and punctuation"\n'
        )

    def run_wizard(self, entered):
        output = io.StringIO()
        with patch("configure.ROOT", self.root), patch("configure.getpass", return_value=entered) as prompt, \
                patch("builtins.input", side_effect=AssertionError("Unexpected visible prompt")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = configure_pexels()
        self.assertIn("输入不显示字符", prompt.call_args.args[0])
        visible = output.getvalue() + prompt.call_args.args[0]
        for value in ("test-old-key", "test-pexels-key", "test-model-key", "test-search-key", "test-vision-key"):
            self.assertNotIn(value, visible)
        return result, visible

    def test_settings_load_strips_key_environment_overrides_file_and_repr_is_hidden(self):
        self.path.write_text('PEXELS_API_KEY="  test-old-key  "\n', encoding="utf-8")
        with patch("app.config.ROOT", self.root):
            settings = Settings.load()
        self.assertEqual(settings.pexels_api_key, "test-old-key")
        with patch.dict(os.environ, {"PEXELS_API_KEY": "  test-pexels-key  "}):
            with patch("app.config.ROOT", self.root):
                overridden = Settings.load()
        self.assertEqual(overridden.pexels_api_key, "test-pexels-key")
        visible = repr(overridden) + str(overridden.status())
        self.assertNotIn("test-pexels-key", visible)
        self.assertEqual(overridden.status()["KEYWORD_IMAGE_SEARCH"], "已配置")
        self.assertEqual(overridden.status()["IMAGE_SEARCH"], "待配置")
        self.assertEqual(Settings().status()["KEYWORD_IMAGE_SEARCH"], "待配置")

    def test_privacy_rules_reject_public_key_and_include_local_key_matching(self):
        self.assertIn("PEXELS_API_KEY", PRIVATE_FIELDS)
        self.assertTrue(inspect_text(".env.example", "PEXELS_API_KEY=test-pexels-key\n"))
        self.assertFalse(inspect_text(".env.example", "PEXELS_API_KEY=\n"))
        self.path.write_text("PEXELS_API_KEY=test-pexels-key\n", encoding="utf-8")
        self.assertIn("test-pexels-key", local_private_values(self.root))

    def test_wizard_changes_only_one_field_preserving_content_and_line_endings(self):
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)):
                original = self.original.replace("\n", newline)
                self.path.write_bytes(original.encode("utf-8"))
                result, visible = self.run_wizard(" test-pexels-key ")
                self.assertEqual(result, 0)
                self.assertIn("https://www.pexels.com/api/new/", visible)
                expected = original.replace('PEXELS_API_KEY="test-old-key"', "PEXELS_API_KEY='test-pexels-key'")
                self.assertEqual(self.path.read_bytes(), expected.encode("utf-8"))
                self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".env"])

    def test_empty_input_preserves_existing_key_without_rewriting(self):
        self.path.write_text(self.original, encoding="utf-8")
        original = self.path.read_bytes()
        modified = self.path.stat().st_mtime_ns
        result, _ = self.run_wizard("")
        self.assertEqual(result, 0)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.path.stat().st_mtime_ns, modified)

    def test_missing_key_without_input_fails_without_writing(self):
        for content in (None, 'CUSTOM_FIELD="keep"\n', 'PEXELS_API_KEY=""\n'):
            with self.subTest(content=content):
                self.path.unlink(missing_ok=True)
                if content is not None:
                    self.path.write_text(content, encoding="utf-8")
                result, _ = self.run_wizard("")
                self.assertEqual(result, 2)
                if content is None:
                    self.assertFalse(self.path.exists())
                else:
                    self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_dash_clears_key_without_touching_other_settings(self):
        self.path.write_text(self.original, encoding="utf-8")
        result, _ = self.run_wizard("-")
        self.assertEqual(result, 0)
        values = dotenv_values(self.path)
        self.assertEqual(values["PEXELS_API_KEY"], "")
        self.assertEqual(values["LLM_API_KEY"], "test-model-key")
        self.assertEqual(values["SERPAPI_API_KEY"], "test-search-key")

    def test_control_characters_fail_without_writing_or_echoing(self):
        self.path.write_text(self.original, encoding="utf-8")
        original = self.path.read_bytes()
        for value in ("private\nvalue", "private\x00value", "private\x7fvalue"):
            result, visible = self.run_wizard(value)
            self.assertEqual(result, 2)
            self.assertNotIn(value, visible)
            self.assertEqual(self.path.read_bytes(), original)

    def test_update_failure_preserves_original_and_cleans_temporary_copy(self):
        self.path.write_text(self.original, encoding="utf-8")
        original = self.path.read_bytes()
        with patch("configure.set_key", side_effect=OSError("test-private-error")):
            with self.assertRaises(OSError):
                self.run_wizard("test-pexels-key")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".env"])

    def test_cli_routes_to_independent_pexels_wizard(self):
        with patch("configure.configure_pexels", return_value=7) as wizard, \
                patch("configure.configure", side_effect=AssertionError("Full wizard called")), \
                patch("configure.configure_groups", side_effect=AssertionError("Group wizard called")):
            self.assertEqual(main(["--pexels"]), 7)
        wizard.assert_called_once_with()

    def test_cli_modes_are_mutually_exclusive(self):
        for mode in ("--check", "--groups"):
            with self.subTest(mode=mode), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    main(["--pexels", mode])
                self.assertEqual(failure.exception.code, 2)
