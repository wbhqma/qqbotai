import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
    PrivateMessageEvent,
)

from app.chat import ChatService
from app.commands import build_help
from app.config import Settings


class OneBotTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        nonebot.init(driver="~none", log_level="WARNING")
        cls.plugin = (
            nonebot.get_plugin("qq_chat") or nonebot.load_plugin("plugins.qq_chat")
        ).module

    def event(self, *, text="/ping", mention="10000", user=30000, pictures=0):
        message = Message()
        if mention:
            message += MessageSegment.at(mention)
        message += MessageSegment.text(text)
        for _ in range(pictures):
            message += MessageSegment(
                "image", {"file": "example.jpg", "url": "https://gchat.qpic.cn/image"}
            )
        return GroupMessageEvent(
            time=0,
            self_id=10000,
            post_type="message",
            sub_type="normal",
            user_id=user,
            group_id=20000,
            message_id=1,
            message_type="group",
            message=message,
            raw_message=str(message),
            font=0,
            sender={"user_id": user},
            to_me=True,
        )

    async def asyncSetUp(self):
        self.bot = Bot(SimpleNamespace(), "10000")
        self.bot.send = AsyncMock()
        self.model = SimpleNamespace(complete=AsyncMock(return_value="聊天回复"))
        self.service = ChatService(
            Settings(allowed_groups=frozenset({"20000"}), cooldown_seconds=0), self.model
        )
        self.plugin.set_service(self.service)
        self.images = SimpleNamespace(process=AsyncMock(return_value="图片分析"))
        self.plugin.set_images(self.images)

    async def test_only_explicit_group_at_matches_even_after_adapter_removes_at(self):
        event = self.event()
        event.message.pop(0)
        self.assertTrue(await self.plugin.chat.rule(self.bot, event, {}))
        for mention in (None, "all", "99999"):
            self.assertFalse(await self.plugin.chat.rule(self.bot, self.event(mention=mention), {}))
        private = PrivateMessageEvent(
            time=0,
            self_id=10000,
            post_type="message",
            sub_type="friend",
            user_id=30000,
            message_id=2,
            message_type="private",
            message="/ping",
            raw_message="/ping",
            font=0,
            sender={"user_id": 30000},
        )
        self.assertFalse(await self.plugin.chat.rule(self.bot, private, {}))

    async def test_ping_and_literal_text_reply(self):
        event = self.event()
        await self.plugin.handle_group_message(self.bot, event)
        self.bot.send.assert_awaited_once_with(
            event, MessageSegment.text("我在线！可以 @我 聊天，或发 /帮助。")
        )

    async def test_bare_at_whitespace_and_help_show_the_same_menu_without_external_calls(self):
        web = SimpleNamespace(search=AsyncMock())
        photos = SimpleNamespace(search=AsyncMock())
        self.plugin.set_websearch(web)
        self.plugin.set_pexels(photos)
        self.addCleanup(self.plugin.set_websearch, None)
        self.addCleanup(self.plugin.set_pexels, None)
        expected = MessageSegment.text(build_help(self.service.settings))
        for text in ("", " \n\t", "/帮助", "/help", "帮助"):
            with self.subTest(text=text):
                self.service.seen.clear()
                self.bot.send.reset_mock()
                event = self.event(text=text)
                event.message.pop(0)
                await self.plugin.handle_group_message(self.bot, event)
                self.bot.send.assert_awaited_once_with(event, expected)
        self.model.complete.assert_not_awaited()
        self.images.process.assert_not_awaited()
        web.search.assert_not_awaited()
        photos.search.assert_not_awaited()
        self.assertFalse(self.service.sessions)

    async def test_bare_at_still_obeys_explicit_at_account_and_group_restrictions(self):
        for mention in (None, "all", "99999"):
            await self.plugin.handle_group_message(self.bot, self.event(text="", mention=mention))
        for settings, event in (
            (Settings(), self.event(text="")),
            (Settings(allowed_groups=frozenset({"99999"})), self.event(text="")),
            (self.service.settings, self.event(text="", user=10000)),
            (
                Settings(allowed_groups=frozenset({"20000"}), napcat_self_id="99999"),
                self.event(text=""),
            ),
        ):
            self.plugin.set_service(ChatService(settings, self.model))
            await self.plugin.handle_group_message(self.bot, event)
        self.bot.send.assert_not_awaited()
        self.model.complete.assert_not_awaited()
        self.images.process.assert_not_awaited()

    async def test_repeated_bare_at_is_deduplicated(self):
        event = self.event(text="")
        await self.plugin.handle_group_message(self.bot, event)
        await self.plugin.handle_group_message(self.bot, event)
        self.bot.send.assert_awaited_once()

    async def test_image_without_text_still_analyzes_image_instead_of_showing_menu(self):
        await self.plugin.handle_group_message(self.bot, self.event(text="", pictures=1))
        self.images.process.assert_awaited_once_with("https://gchat.qpic.cn/image", "analyze", "")
        self.assertEqual(self.bot.send.call_args.args[1], MessageSegment.text("图片分析"))
        self.model.complete.assert_not_awaited()

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
            await self.plugin.handle_group_message(
                self.bot, self.event(text="/搜图", pictures=count)
            )
        self.images.process.assert_not_awaited()

    async def test_model_cq_text_cannot_become_an_at_or_image_segment(self):
        self.images.process.return_value = "[CQ:at,qq=all] [CQ:image,file=private]"
        await self.plugin.handle_group_message(self.bot, self.event(text="/识图", pictures=1))
        segment = self.bot.send.call_args.args[1]
        self.assertEqual(segment.type, "text")
        self.assertEqual(segment.data["text"], self.images.process.return_value)
