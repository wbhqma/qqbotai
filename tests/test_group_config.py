import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dotenv import dotenv_values

from configure import configure_groups, main


class GroupConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / ".env"
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.original = (
            '# preserve this comment\n'
            'ONEBOT_ACCESS_TOKEN="0123456789abcdef"\n'
            'NAPCAT_ALLOWED_GROUPS="20000"\n'
            'LLM_PROVIDER="compatible"\n'
            'LLM_BASE_URL="https://test-model.example/v1"\n'
            'LLM_MODEL="test-model-name"\n'
            'LLM_API_KEY="test-model-key"\n'
            'CUSTOM_FIELD="keep arbitrary content # and spaces"\n'
        )

    def run_groups(self, answer):
        output = io.StringIO()
        with patch("configure.ROOT", self.root), patch("configure.getpass", return_value=answer) as prompt, \
                patch("builtins.input", side_effect=AssertionError("Unexpected visible prompt")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = configure_groups()
        self.assertIn("输入不显示字符", prompt.call_args.args[0])
        visible = output.getvalue() + prompt.call_args.args[0]
        for value in ("20000", "30000", "40000", "test-model-key", "0123456789abcdef", "test-model-name"):
            self.assertNotIn(value, visible)
        return result, visible

    def test_changes_only_group_field_and_preserves_other_content_and_line_endings(self):
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)):
                original = self.original.replace("\n", newline)
                self.path.write_bytes(original.encode("utf-8"))
                result, _ = self.run_groups(" 30000, 40000 ")
                self.assertEqual(result, 0)
                updated = self.path.read_bytes().decode("utf-8")
                expected = original.replace('NAPCAT_ALLOWED_GROUPS="20000"', "NAPCAT_ALLOWED_GROUPS='30000,40000'")
                self.assertEqual(updated, expected)
                self.assertEqual(dotenv_values(self.path)["NAPCAT_ALLOWED_GROUPS"], "30000,40000")
                self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".env"])

    def test_invalid_input_does_not_write_or_echo(self):
        self.path.write_text(self.original, encoding="utf-8")
        original = self.path.read_bytes()
        for answer in ("private-bad-group", "１２３４５", "123;456", ", ,"):
            with self.subTest(answer=answer):
                result, visible = self.run_groups(answer)
                self.assertEqual(result, 2)
                self.assertNotIn(answer, visible)
                self.assertEqual(self.path.read_bytes(), original)

    def test_empty_input_preserves_valid_existing_field_without_rewriting(self):
        self.path.write_text(self.original, encoding="utf-8")
        original = self.path.read_bytes()
        modified = self.path.stat().st_mtime_ns
        result, _ = self.run_groups("")
        self.assertEqual(result, 0)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.path.stat().st_mtime_ns, modified)

    def test_empty_input_without_existing_group_fails_without_writing(self):
        for content in (None, 'CUSTOM_FIELD="keep"\n', 'NAPCAT_ALLOWED_GROUPS=""\n'):
            with self.subTest(content=content):
                self.path.unlink(missing_ok=True)
                if content is not None:
                    self.path.write_text(content, encoding="utf-8")
                result, _ = self.run_groups("")
                self.assertEqual(result, 2)
                if content is None:
                    self.assertFalse(self.path.exists())
                else:
                    self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_failed_update_leaves_original_file_and_no_temporary_copy(self):
        self.path.write_text(self.original, encoding="utf-8")
        original = self.path.read_bytes()
        with patch("configure.set_key", side_effect=OSError("test-private-error")):
            with self.assertRaises(OSError):
                self.run_groups("30000")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".env"])

    def test_cli_routes_only_to_the_group_wizard(self):
        with patch("configure.configure_groups", return_value=7) as groups, \
                patch("configure.configure", side_effect=AssertionError("Full wizard called")), \
                patch("configure.check_configuration", side_effect=AssertionError("Full check called")):
            self.assertEqual(main(["--groups"]), 7)
        groups.assert_called_once_with()
