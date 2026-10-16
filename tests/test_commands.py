import unittest

from app.commands import build_help
from app.config import Settings


class HelpMenuTests(unittest.TestCase):
    def test_all_features_remain_visible_when_optional_services_are_missing(self):
        menu = build_help(Settings())
        for command in ("/帮助", "/ping", "/清空", "/搜索", "/识图", "/查出处", "/找图", "/搜图"):
            with self.subTest(command=command):
                self.assertIn(command, menu)
        self.assertEqual(menu.count("［未配置］"), 5)
        self.assertIn("同一条消息", menu)
        self.assertIn("重启清空", menu)

    def test_configuration_state_does_not_expose_credentials_or_identifiers(self):
        settings = Settings(
            llm_api_key="test-chat-key",
            vision_model="test-vision-model",
            vision_base_url="https://example.org/v1",
            vision_api_key="test-vision-key",
            saucenao_api_key="test-source-key",
            pexels_api_key="test-photo-key",
            tavily_api_key="test-web-key",
            onebot_access_token="test-local-token",
            allowed_groups=frozenset({"20000"}),
            napcat_self_id="10000",
        )
        menu = build_help(settings)
        self.assertEqual(menu.count("［已配置］"), 5)
        for value in (
            settings.llm_api_key,
            settings.vision_model,
            settings.vision_base_url,
            settings.vision_api_key,
            settings.saucenao_api_key,
            settings.pexels_api_key,
            settings.tavily_api_key,
            settings.onebot_access_token,
            settings.napcat_self_id,
            *settings.allowed_groups,
        ):
            self.assertNotIn(value, menu)

    def test_local_models_need_no_key_and_serpapi_can_provide_source_lookup(self):
        settings = Settings(
            llm_provider="ollama",
            llm_model="test-local-model",
            vision_provider="ollama",
            vision_model="test-local-vision",
            serpapi_api_key="test-serp-key",
        )
        menu = build_help(settings)
        self.assertEqual(menu.count("［已配置］"), 3)
        self.assertEqual(menu.count("［未配置］"), 2)
