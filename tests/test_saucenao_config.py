import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dotenv import dotenv_values

from app.config import Settings
from configure import configure_saucenao, main
from scripts.check_privacy import PRIVATE_FIELDS, inspect_text, local_private_values


class SauceNaoConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / ".env"
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.original = (
            "# preserve unrelated services and formatting\n"
            'LLM_API_KEY="test-model-key"\n'
            'VISION_PROVIDER="compatible"\n'
            'VISION_BASE_URL="https://vision.example/v1"\n'
            'VISION_MODEL="test-vision"\n'
            'VISION_API_KEY="test-vision-key"\n'
            'PEXELS_API_KEY="test-pexels-key"\n'
            'TAVILY_API_KEY="test-tavily-key"\n'
            'SAUCENAO_API_KEY="test-old-key"\n'
            'CUSTOM_FIELD="keep spaces # and punctuation"\n'
        )

    def run_wizard(self, entered):
        output = io.StringIO()
        with (
            patch("configure.ROOT", self.root),
            patch("configure.getpass", return_value=entered) as prompt,
            patch("builtins.input", side_effect=AssertionError("Unexpected visible prompt")),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            result = configure_saucenao()
        self.assertIn("输入不显示字符", prompt.call_args.args[0])
        visible = output.getvalue() + prompt.call_args.args[0]
        for value in (
            "test-old-key",
            "test-saucenao-key",
            "test-model-key",
            "test-pexels-key",
            "test-vision-key",
            "test-tavily-key",
        ):
            self.assertNotIn(value, visible)
        return result, visible

    def test_settings_load_environment_precedence_stripping_and_safe_status(self):
        self.path.write_text('SAUCENAO_API_KEY="  test-old-key  "\n', encoding="utf-8")
        with patch("app.config.ROOT", self.root):
            settings = Settings.load()
        self.assertEqual(settings.saucenao_api_key, "test-old-key")
        with patch.dict(os.environ, {"SAUCENAO_API_KEY": "  test-saucenao-key  "}):
            with patch("app.config.ROOT", self.root):
                overridden = Settings.load()
        self.assertEqual(overridden.saucenao_api_key, "test-saucenao-key")
        visible = repr(overridden) + str(overridden.status())
        self.assertNotIn("test-saucenao-key", visible)
        self.assertEqual(overridden.status()["REVERSE_IMAGE_SEARCH"], "已配置")
        self.assertEqual(overridden.status()["KEYWORD_IMAGE_SEARCH"], "待配置")
        self.assertEqual(Settings().status()["REVERSE_IMAGE_SEARCH"], "待配置")

    def test_privacy_rules_cover_public_templates_and_local_key_matching(self):
        self.assertIn("SAUCENAO_API_KEY", PRIVATE_FIELDS)
        self.assertTrue(inspect_text(".env.example", "SAUCENAO_API_KEY=test-saucenao-key\n"))
        self.assertFalse(inspect_text(".env.example", "SAUCENAO_API_KEY=\n"))
        self.path.write_text("SAUCENAO_API_KEY=test-saucenao-key\n", encoding="utf-8")
        self.assertIn("test-saucenao-key", local_private_values(self.root))

    def test_updates_only_key_preserving_vision_and_other_content_and_line_endings(self):
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)):
                original = self.original.replace("\n", newline)
                self.path.write_bytes(original.encode("utf-8"))
                result, visible = self.run_wizard(" test-saucenao-key ")
                self.assertEqual(result, 0)
                self.assertIn("https://saucenao.com/user.php?page=search-api", visible)
                expected = original.replace(
                    'SAUCENAO_API_KEY="test-old-key"', "SAUCENAO_API_KEY='test-saucenao-key'"
                )
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

    def test_empty_input_without_existing_key_fails_without_writing(self):
        for content in (None, 'CUSTOM_FIELD="keep"\n', 'SAUCENAO_API_KEY=""\n'):
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

    def test_dash_clears_key_and_preserves_other_services(self):
        self.path.write_text(self.original, encoding="utf-8")
        result, _ = self.run_wizard("-")
        self.assertEqual(result, 0)
        values = dotenv_values(self.path)
        self.assertEqual(values["SAUCENAO_API_KEY"], "")
        self.assertEqual(values["VISION_API_KEY"], "test-vision-key")
        self.assertEqual(values["PEXELS_API_KEY"], "test-pexels-key")

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
                self.run_wizard("test-saucenao-key")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".env"])

    def test_cli_routes_only_to_independent_saucenao_wizard(self):
        with (
            patch("configure.configure_saucenao", return_value=7) as wizard,
            patch("configure.configure", side_effect=AssertionError("Full wizard called")),
            patch("configure.configure_pexels", side_effect=AssertionError("Pexels wizard called")),
        ):
            self.assertEqual(main(["--saucenao"]), 7)
        wizard.assert_called_once_with()

    def test_cli_modes_are_mutually_exclusive(self):
        for mode in ("--check", "--groups", "--pexels", "--tavily"):
            with self.subTest(mode=mode), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    main(["--saucenao", mode])
                self.assertEqual(failure.exception.code, 2)

    def test_serpapi_also_counts_as_reverse_search_without_changing_original_status(self):
        serpapi = Settings(serpapi_api_key="test-search-key").status()
        self.assertEqual(serpapi["REVERSE_IMAGE_SEARCH"], "已配置")
        self.assertEqual(serpapi["IMAGE_SEARCH"], "已配置")
        saucenao = Settings(saucenao_api_key="test-saucenao-key").status()
        self.assertEqual(saucenao["REVERSE_IMAGE_SEARCH"], "已配置")
        self.assertEqual(saucenao["IMAGE_SEARCH"], "待配置")
