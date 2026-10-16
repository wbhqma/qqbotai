import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from configure import main


class LauncherConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / ".env"
        self.values = {
            "ONEBOT_ACCESS_TOKEN": "0123456789abcdef",
            "NAPCAT_ALLOWED_GROUPS": "976543210",
            "NAPCAT_SELF_ID": "987654321",
            "LLM_PROVIDER": "compatible",
            "LLM_BASE_URL": "https://private-model.example/v1",
            "LLM_MODEL": "private-model-name",
            "LLM_API_KEY": "test-model-key",
            "BOT_NAME": "private-bot-name",
        }
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def run_check(self):
        output = io.StringIO()
        with patch("app.config.ROOT", self.root), \
                patch("configure.configure", side_effect=AssertionError("Interactive wizard called")), \
                patch("builtins.input", side_effect=AssertionError("Interactive input called")), \
                patch("configure.getpass", side_effect=AssertionError("Secret prompt called")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = main(["--check"])
        visible = output.getvalue()
        for value in self.values.values():
            self.assertNotIn(value, visible)
        self.assertNotIn("Traceback", visible)
        return result, visible

    def write_config(self, values):
        self.path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")

    def test_complete_local_configuration_is_read_only_and_noninteractive(self):
        self.write_config(self.values)
        original = self.path.read_bytes()
        modified = self.path.stat().st_mtime_ns
        code, output = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn("检查通过", output)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.path.stat().st_mtime_ns, modified)

    def test_missing_configuration_returns_two_without_creating_files(self):
        code, output = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn("配置未就绪", output)
        self.assertFalse(self.path.exists())

    def test_missing_token_or_groups_and_invalid_fields_are_safe(self):
        cases = (
            {"ONEBOT_ACCESS_TOKEN": ""},
            {"ONEBOT_ACCESS_TOKEN": "private-short"},
            {"NAPCAT_ALLOWED_GROUPS": ""},
            {"NAPCAT_ALLOWED_GROUPS": "private-invalid-group"},
            {"NAPCAT_SELF_ID": "private-invalid-account"},
            {"NAPCAT_PORT": "private-invalid-port"},
            {"NAPCAT_PORT": "1"},
            {"LLM_BASE_URL": "https://user:private-password@example.com"},
            {"LLM_EXTRA_BODY": "private-invalid-json"},
        )
        for changes in cases:
            with self.subTest(fields=tuple(changes)), patch.dict(os.environ, {}, clear=True):
                values = {**self.values, **changes}
                self.write_config(values)
                original = self.path.read_bytes()
                code, output = self.run_check()
                self.assertEqual(code, 2)
                self.assertIn("配置未就绪", output)
                for value in changes.values():
                    if value:
                        self.assertNotIn(value, output)
                self.assertEqual(self.path.read_bytes(), original)

    def test_environment_configuration_does_not_require_a_local_file(self):
        with patch.dict(os.environ, self.values, clear=True):
            code, _ = self.run_check()
        self.assertEqual(code, 0)
        self.assertFalse(self.path.exists())

    def test_key_can_be_filled_later_for_offline_ping_setup(self):
        values = {**self.values, "LLM_API_KEY": ""}
        self.write_config(values)
        code, _ = self.run_check()
        self.assertEqual(code, 0)

    def test_default_command_preserves_the_existing_wizard(self):
        with patch("configure.configure", return_value=7) as wizard:
            self.assertEqual(main([]), 7)
        wizard.assert_called_once_with()
