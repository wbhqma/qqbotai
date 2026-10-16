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
from app.pexels import PhotoResult


class KeywordImageTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder):
            nonebot.init(driver="~none", log_level="WARNING")
        cls.plugin = (nonebot.get_plugin("qq_chat") or nonebot.load_plugin("plugins.qq_chat")).module

    async def asyncSetUp(self):
        self.bot = Bot(SimpleNamespace(), "10000")
        self.bot.send = AsyncMock()
        self.model = SimpleNamespace(complete=AsyncMock(side_effect=AssertionError("Text model must not be called")))
        self.service = ChatService(Settings(allowed_groups=frozenset({"20000"}), cooldown_seconds=0), self.model)
        self.plugin.set_service(self.service)
        self.images = SimpleNamespace(process=AsyncMock(return_value="图片出处"))
        self.plugin.set_images(self.images)
        self.pexels = SimpleNamespace(search=AsyncMock(return_value=PhotoResult(
            caption="摄影师：示例作者 · Pexels\nhttps://www.pexels.com/photo/example-1/", image=b"sample-jpeg")))
        self.plugin.set_pexels(self.pexels)
        self.addCleanup(self.plugin.set_pexels, None)

    def event(self, *, text="/找图 猫", group=20000, user=30000, mention=True, picture=False, message_id=1):
        message = Message()
        if mention:
            message += MessageSegment.at("10000")
        message += MessageSegment.text(text)
        if picture:
            message += MessageSegment("image", {"url": "https://gchat.qpic.cn/image", "file": "image.jpg"})
        return GroupMessageEvent(time=0, self_id=10000, post_type="message", sub_type="normal",
                                 user_id=user, group_id=group, message_id=message_id, message_type="group",
                                 message=message, raw_message=str(message), font=0, sender={"user_id": user})

    async def test_keyword_aliases_send_photo_and_credit_without_text_model_or_history(self):
        for command in ("/找图", "/搜图"):
            with self.subTest(command=command):
                self.service.seen.clear()
                self.bot.send.reset_mock()
                self.pexels.search.reset_mock()
                event = self.event(text=command + " 猫 海边")
                event.message.pop(0)
                await self.plugin.handle_group_message(self.bot, event)
                self.pexels.search.assert_awaited_once_with("猫 海边")
                reply = self.bot.send.call_args.args[1]
                self.assertEqual([segment.type for segment in reply], ["text", "image"])
                self.assertIn("Pexels", reply[0].data["text"])
                self.assertTrue(reply[1].data["file"].startswith("base64://"))
                self.assertEqual(self.service.sessions[("10000", "20000", "30000")].messages, [])
        self.model.complete.assert_not_awaited()
        self.images.process.assert_not_awaited()

    async def test_duplicate_event_and_cooldown_do_not_search_again(self):
        self.plugin.set_service(self.service)
        event = self.event()
        await self.plugin.handle_group_message(self.bot, event)
        await self.plugin.handle_group_message(self.bot, event)
        self.pexels.search.assert_awaited_once()
        self.bot.send.assert_awaited_once()
        self.service.settings = Settings(allowed_groups=frozenset({"20000"}), cooldown_seconds=60)
        await self.plugin.handle_group_message(self.bot, self.event(message_id=2))
        self.pexels.search.assert_awaited_once()
        self.assertIn("慢", self.bot.send.call_args.args[1].data["text"])

    async def test_permissions_and_missing_mention_do_not_search(self):
        for event in (self.event(group=29999), self.event(user=10000), self.event(mention=False)):
            await self.plugin.handle_group_message(self.bot, event)
        self.pexels.search.assert_not_awaited()
        self.bot.send.assert_not_awaited()

    async def test_missing_keywords_and_attached_photo_show_usage_without_search(self):
        for event in (self.event(text="/找图"), self.event(text="/搜图"), self.event(picture=True)):
            await self.plugin.handle_group_message(self.bot, event)
        self.pexels.search.assert_not_awaited()
        self.model.complete.assert_not_awaited()
        self.images.process.assert_not_awaited()
        self.assertIn("/找图", self.bot.send.call_args.args[1].data["text"])

    async def test_existing_reverse_search_with_picture_is_preserved(self):
        await self.plugin.handle_group_message(self.bot, self.event(text="/搜图", picture=True))
        self.images.process.assert_awaited_once_with("https://gchat.qpic.cn/image", "search", "/搜图")
        self.pexels.search.assert_not_awaited()

    async def test_unconfigured_search_returns_literal_message_without_picture(self):
        self.pexels.search.side_effect = ModelError("Pexels 关键词找图尚未配置。")
        await self.plugin.handle_group_message(self.bot, self.event())
        reply = self.bot.send.call_args.args[1]
        self.assertEqual(reply.type, "text")
        self.assertIn("尚未配置", reply.data["text"])
        self.model.complete.assert_not_awaited()

    async def test_failed_download_returns_credit_links_without_image(self):
        self.pexels.search.return_value = PhotoResult(caption="Pexels 来源链接", image=None)
        await self.plugin.handle_group_message(self.bot, self.event())
        reply = self.bot.send.call_args.args[1]
        self.assertEqual(reply.type, "text")
        self.assertIn("Pexels", reply.data["text"])

    async def test_caption_cq_strings_are_not_interpreted_as_control_segments(self):
        self.pexels.search.return_value = PhotoResult(caption="[CQ:at,qq=all] 摄影师 · Pexels", image=b"image")
        await self.plugin.handle_group_message(self.bot, self.event())
        reply = self.bot.send.call_args.args[1]
        self.assertEqual([segment.type for segment in reply], ["text", "image"])
        self.assertIn("[CQ:at,qq=all]", reply[0].data["text"])

    async def test_qq_send_failure_is_retryable_and_does_not_create_history(self):
        self.bot.send.side_effect = RuntimeError("test-failure")
        event = self.event()
        await self.plugin.handle_group_message(self.bot, event)
        self.bot.send.side_effect = None
        await self.plugin.handle_group_message(self.bot, event)
        self.assertEqual(self.pexels.search.await_count, 2)
        self.assertEqual(self.service.sessions[("10000", "20000", "30000")].messages, [])
