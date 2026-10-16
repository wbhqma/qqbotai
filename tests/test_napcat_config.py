import unittest

from app.config import Settings
from scripts.check_privacy import inspect_text


class NapCatConfigTests(unittest.TestCase):
    def test_account_access_requires_token_and_group_allowlist(self):
        for settings in (Settings(), Settings(onebot_access_token="0123456789abcdef"),
                         Settings(onebot_access_token="short", allowed_groups=frozenset({"20000"})),
                         Settings(onebot_access_token="0123456789abcdef", allowed_groups=frozenset({"not-a-number"})),
                         Settings(onebot_access_token="0123456789abcdef", allowed_groups=frozenset({"20000"}), napcat_self_id="not-a-number")):
            with self.assertRaises(ValueError):
                settings.validate_napcat()
        Settings(onebot_access_token="0123456789abcdef", allowed_groups=frozenset({"20000"})).validate_napcat()

    def test_vision_credentials_are_independent_and_hidden(self):
        settings = Settings(llm_api_key="test-text-key", vision_provider="compatible",
                            vision_base_url="https://private-vision.example/v1", vision_model="test-vision-model",
                            vision_api_key="test-vision-key", serpapi_api_key="test-search-key",
                            onebot_access_token="test-onebot-token", napcat_self_id="10000")
        visible = repr(settings) + repr(settings.resolve_vision()) + str(settings.status())
        for value in ("test-text-key", "test-vision-key", "test-search-key", "test-onebot-token", "private-vision.example", "test-vision-model", "10000"):
            self.assertNotIn(value, visible)
        self.assertIsNone(Settings(llm_api_key="test-text-key").resolve_vision())
        self.assertEqual(Settings(vision_provider="ollama", vision_model="test-vision").resolve_vision().api_key, "")

    def test_public_templates_cannot_include_new_private_fields(self):
        for name in ("ONEBOT_ACCESS_TOKEN", "VISION_API_KEY", "SERPAPI_API_KEY", "NAPCAT_SELF_ID", "NAPCAT_ALLOWED_GROUPS"):
            self.assertTrue(inspect_text(".env.example", name + "=test-private-value"))
