import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.config import Settings
from app.napcat import prepare


class NapCatPrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.env = self.root / ".env"
        self.env.write_text("ONEBOT_ACCESS_TOKEN=0123456789abcdef\nNAPCAT_PORT=8082\n", encoding="utf-8")
        self.workdir = self.root / "runtime"

    def test_default_account_template_uses_local_connection_and_separate_panel_token(self):
        prepare(self.env, self.workdir)
        config = json.loads((self.workdir / "config/onebot11.json").read_text(encoding="utf-8"))
        client = config["network"]["websocketClients"][0]
        self.assertEqual(client["url"], "ws://127.0.0.1:8082/onebot/v11/")
        self.assertEqual(client["token"], "0123456789abcdef")
        self.assertEqual(client["messagePostFormat"], "array")
        panel = json.loads((self.workdir / "config/webui.json").read_text(encoding="utf-8"))
        self.assertEqual(panel["host"], "127.0.0.1")
        self.assertGreaterEqual(len(panel["token"]), 16)
        self.assertNotEqual(panel["token"], client["token"])

    def test_existing_account_config_is_merged_and_original_is_backed_up(self):
        folder = self.workdir / "config"
        folder.mkdir(parents=True)
        path = folder / "onebot11_10000.json"
        original = {"custom": True, "network": {"websocketClients": [
            {"name": "other-client", "enable": False}, {"name": "qqbotai-local", "token": "old"}],
            "httpServers": [{"name": "existing-server"}]}}
        path.write_text(json.dumps(original), encoding="utf-8")
        prepare(self.env, self.workdir)
        updated = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(updated["custom"])
        self.assertEqual(updated["network"]["websocketClients"][0]["name"], "other-client")
        self.assertEqual(len(updated["network"]["websocketClients"]), 2)
        self.assertEqual(updated["network"]["httpServers"], original["network"]["httpServers"])
        self.assertEqual(json.loads(path.with_suffix(".json.bak").read_text(encoding="utf-8")), original)

    def test_repeated_prepare_is_idempotent_and_keeps_panel_token(self):
        prepare(self.env, self.workdir)
        path = self.workdir / "config/webui.json"
        first = path.read_bytes()
        prepare(self.env, self.workdir)
        self.assertEqual(path.read_bytes(), first)
        self.assertFalse(path.with_suffix(".json.bak").exists())

    def test_invalid_account_file_does_not_update_any_other_file(self):
        folder = self.workdir / "config"
        folder.mkdir(parents=True)
        (folder / "onebot11_10000.json").write_text("invalid", encoding="utf-8")
        with self.assertRaises(ValueError):
            prepare(self.env, self.workdir)
        self.assertFalse((folder / "onebot11.json").exists())

    def test_missing_token_and_invalid_port_do_not_write_config(self):
        for content in ("ONEBOT_ACCESS_TOKEN=short\n", "ONEBOT_ACCESS_TOKEN=0123456789abcdef\nNAPCAT_PORT=bad\n"):
            self.env.write_text(content, encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
                prepare(self.env, self.workdir)
            self.assertFalse(self.workdir.exists())

    def test_environment_overrides_match_server_settings(self):
        with patch.dict(os.environ, {"ONEBOT_ACCESS_TOKEN": "fedcba9876543210", "NAPCAT_PORT": "8093"}):
            prepare(self.env, self.workdir)
            with patch("app.config.ROOT", self.root):
                settings = Settings.load()
        client = json.loads((self.workdir / "config/onebot11.json").read_text(encoding="utf-8"))["network"]["websocketClients"][0]
        self.assertEqual(client["token"], settings.onebot_access_token)
        self.assertEqual(client["url"], f"ws://127.0.0.1:{settings.napcat_port}/onebot/v11/")
        self.assertEqual(settings.napcat_port, 8093)

    def test_quoted_token_whitespace_matches_server_settings(self):
        self.env.write_text('ONEBOT_ACCESS_TOKEN="  0123456789abcdef  "\nNAPCAT_PORT=8082\n', encoding="utf-8")
        prepare(self.env, self.workdir)
        with patch("app.config.ROOT", self.root):
            settings = Settings.load()
        client = json.loads((self.workdir / "config/onebot11.json").read_text(encoding="utf-8"))["network"]["websocketClients"][0]
        self.assertEqual(client["token"], settings.onebot_access_token)
        self.assertEqual(client["token"], "0123456789abcdef")
