import contextlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment

from app.chat import ChatService
from app.config import Settings
from app.llm import ModelError


class WebSearchRoutingTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder):
            nonebot.init(driver="~none", log_level="WARNING")
        cls.plugin = (
            nonebot.get_plugin("qq_chat") or nonebot.load_plugin("plugins.qq_chat")
        ).module

    async def asyncSetUp(self):
        self.bot = Bot(SimpleNamespace(), "10000")
        self.bot.send = AsyncMock()
        self.model = SimpleNamespace(complete=AsyncMock(return_value="普通聊天回复"))
        self.service = ChatService(
            Settings(allowed_groups=frozenset({"20000"}), cooldown_seconds=0), self.model
        )
        self.plugin.set_service(self.service)
        self.web = SimpleNamespace(
            search=AsyncMock(return_value="检索总结\n来源：https://example.org/article")
        )
        self.plugin.set_websearch(self.web)
        self.addCleanup(self.plugin.set_websearch, None)

    def event(
        self,
        *,
        text="/搜索 青岛天气",
        group=20000,
        user=30000,
        mention=True,
        picture=False,
        message_id=1,
    ):
        message = Message()
        if mention:
            message += MessageSegment.at("10000")
        message += MessageSegment.text(text)
        if picture:
            message += MessageSegment(
                "image", {"file": "test.jpg", "url": "https://gchat.qpic.cn/image"}
            )
        return GroupMessageEvent(
            time=0,
            self_id=10000,
            post_type="message",
            sub_type="normal",
            user_id=user,
            group_id=group,
            message_id=message_id,
            message_type="group",
            message=message,
            raw_message=str(message),
            font=0,
            sender={"user_id": user},
        )

    async def test_aliases_search_only_question_and_do_not_store_results_in_history(self):
        for command in ("/搜索", "/联网", "/search"):
            self.service.seen.clear()
            self.web.search.reset_mock()
            event = self.event(text=command + " 青岛 今天的天气")
            event.message.pop(0)
            await self.plugin.handle_group_message(self.bot, event)
            self.web.search.assert_awaited_once_with("青岛 今天的天气")
            self.assertEqual(self.bot.send.call_args.args[1].type, "text")
            self.assertEqual(self.service.sessions[("10000", "20000", "30000")].messages, [])
        self.model.complete.assert_not_awaited()

    async def test_wrong_group_self_and_missing_at_never_search(self):
        for event in (self.event(group=29999), self.event(user=10000), self.event(mention=False)):
            await self.plugin.handle_group_message(self.bot, event)
        self.web.search.assert_not_awaited()
        self.bot.send.assert_not_awaited()

    async def test_missing_question_and_attached_picture_show_usage_without_search(self):
        for event in (self.event(text="/搜索"), self.event(picture=True)):
            await self.plugin.handle_group_message(self.bot, event)
        self.web.search.assert_not_awaited()
        self.model.complete.assert_not_awaited()
        self.assertIn("/搜索", self.bot.send.call_args.args[1].data["text"])

    async def test_duplicate_event_and_cooldown_prevent_repeated_external_calls(self):
        event = self.event()
        await self.plugin.handle_group_message(self.bot, event)
        await self.plugin.handle_group_message(self.bot, event)
        self.web.search.assert_awaited_once()
        self.bot.send.assert_awaited_once()
        self.service.settings = Settings(allowed_groups=frozenset({"20000"}), cooldown_seconds=60)
        await self.plugin.handle_group_message(self.bot, self.event(message_id=2))
        self.web.search.assert_awaited_once()
        self.assertIn("慢", self.bot.send.call_args.args[1].data["text"])

    async def test_search_error_does_not_fall_back_to_model_guesses(self):
        self.web.search.side_effect = ModelError("联网搜索尚未配置。")
        await self.plugin.handle_group_message(self.bot, self.event())
        self.assertIn("尚未配置", self.bot.send.call_args.args[1].data["text"])
        self.model.complete.assert_not_awaited()

    async def test_regular_chat_does_not_trigger_external_search(self):
        await self.plugin.handle_group_message(
            self.bot, self.event(text="你好，搜索功能是什么意思")
        )
        self.web.search.assert_not_awaited()
        self.model.complete.assert_awaited_once()

    async def test_untrusted_search_text_cannot_become_cq_control_segments(self):
        self.web.search.return_value = "[CQ:at,qq=all] [CQ:image,file=private]"
        await self.plugin.handle_group_message(self.bot, self.event())
        reply = self.bot.send.call_args.args[1]
        self.assertEqual(reply.type, "text")
        self.assertEqual(reply.data["text"], self.web.search.return_value)
