import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment, PrivateMessageEvent

from app.chat import ChatService
from app.config import Settings


class OneBotTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        nonebot.init(driver="~none", log_level="WARNING")
        cls.plugin = nonebot.load_plugin("plugins.qq_chat").module

    def event(self, *, text="/ping", mention="10000", user=30000, pictures=0):
        message = Message()
        if mention:
            message += MessageSegment.at(mention)
        message += MessageSegment.text(text)
        for _ in range(pictures):
            message += MessageSegment("image", {"file": "example.jpg", "url": "https://gchat.qpic.cn/image"})
        return GroupMessageEvent(time=0, self_id=10000, post_type="message", sub_type="normal",
                                 user_id=user, group_id=20000, message_id=1, message_type="group",
                                 message=message, raw_message=str(message), font=0,
                                 sender={"user_id": user}, to_me=True)

    async def asyncSetUp(self):
        self.bot = Bot(SimpleNamespace(), "10000")
        self.bot.send = AsyncMock()
        self.service = ChatService(Settings(allowed_groups=frozenset({"20000"}), cooldown_seconds=0), SimpleNamespace())
        self.plugin.set_service(self.service)
        self.images = SimpleNamespace(process=AsyncMock(return_value="图片分析"))
        self.plugin.set_images(self.images)

    async def test_only_explicit_group_at_matches_even_after_adapter_removes_at(self):
        event = self.event()
        event.message.pop(0)
        self.assertTrue(await self.plugin.chat.rule(self.bot, event, {}))
        for mention in (None, "all", "99999"):
            self.assertFalse(await self.plugin.chat.rule(self.bot, self.event(mention=mention), {}))
        private = PrivateMessageEvent(time=0, self_id=10000, post_type="message", sub_type="friend",
                                      user_id=30000, message_id=2, message_type="private", message="/ping",
                                      raw_message="/ping", font=0, sender={"user_id": 30000})
        self.assertFalse(await self.plugin.chat.rule(self.bot, private, {}))

    async def test_ping_and_literal_text_reply(self):
        event = self.event()
        await self.plugin.handle_group_message(self.bot, event)
        self.bot.send.assert_awaited_once_with(event, MessageSegment.text("我在线！可以 @我 聊天，或发 /帮助。"))

    async def test_empty_allowlist_wrong_group_self_and_wrong_account_are_ignored(self):
        for settings, event in (
            (Settings(), self.event()),
            (Settings(allowed_groups=frozenset({"99999"})), self.event()),
            (self.service.settings, self.event(user=10000)),
            (Settings(allowed_groups=frozenset({"20000"}), napcat_self_id="99999"), self.event()),
        ):
            self.plugin.set_service(ChatService(settings, SimpleNamespace()))
            await self.plugin.handle_group_message(self.bot, event)
        self.bot.send.assert_not_awaited()

    async def test_image_analysis_search_and_duplicate_event(self):
        for mode, command in (("analyze", "/识图 读一下文字"), ("search", "/搜图")):
            self.service.seen.clear()
            self.images.process.reset_mock()
            event = self.event(text=command, pictures=1)
            await self.plugin.handle_group_message(self.bot, event)
            await self.plugin.handle_group_message(self.bot, event)
            self.images.process.assert_awaited_once()
            self.assertEqual(self.images.process.call_args.args[1], mode)
            self.assertFalse(self.service.sessions[("10000", "20000", "30000")].messages)

    async def test_bad_image_count_does_not_call_image_services(self):
        for count in (0, 2):
            await self.plugin.handle_group_message(self.bot, self.event(text="/搜图", pictures=count))
        self.images.process.assert_not_awaited()

    async def test_model_cq_text_cannot_become_an_at_or_image_segment(self):
        self.images.process.return_value = "[CQ:at,qq=all] [CQ:image,file=private]"
        await self.plugin.handle_group_message(self.bot, self.event(text="/识图", pictures=1))
        segment = self.bot.send.call_args.args[1]
        self.assertEqual(segment.type, "text")
        self.assertEqual(segment.data["text"], self.images.process.return_value)
