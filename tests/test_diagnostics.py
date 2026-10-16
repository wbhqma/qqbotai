import contextlib
import tempfile
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
from app.config import Settings
from app.diagnostics import COUNTERS, Diagnostics, diagnostics


class DiagnosticCounterTests(unittest.TestCase):
    def test_snapshot_has_only_fixed_integer_counters_and_is_a_copy(self):
        counters = Diagnostics()
        visible = counters.snapshot()
        self.assertEqual(set(visible), set(COUNTERS))
        self.assertTrue(all(type(value) is int and value == 0 for value in visible.values()))
        visible["group_events"] = 99
        self.assertEqual(counters.snapshot()["group_events"], 0)
        with self.assertRaises(ValueError):
            counters.increment("private-user-or-message")
        self.assertNotIn("private-user-or-message", counters.snapshot())


class GroupDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # NoneBot 初始化也只在空目录里查找配置，不接触项目真实 .env。
        with tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder):
            nonebot.init(driver="~none", log_level="WARNING")
        cls.plugin = (
            nonebot.get_plugin("qq_chat") or nonebot.load_plugin("plugins.qq_chat")
        ).module

    async def asyncSetUp(self):
        diagnostics.reset()
        self.addCleanup(diagnostics.reset)
        self.bot = Bot(SimpleNamespace(), "10000")
        self.bot.send = AsyncMock()
        self.service = ChatService(
            Settings(allowed_groups=frozenset({"20000"}), cooldown_seconds=0), SimpleNamespace()
        )
        self.plugin.set_service(self.service)
        self.plugin.set_images(SimpleNamespace(process=AsyncMock()))

    def event(self, *, mention=True, group=20000, user=30000, text="/ping"):
        message = Message()
        if mention:
            message += MessageSegment.at("10000")
        message += MessageSegment.text(text)
        return GroupMessageEvent(
            time=0,
            self_id=10000,
            post_type="message",
            sub_type="normal",
            user_id=user,
            group_id=group,
            message_id=1,
            message_type="group",
            message=message,
            raw_message=str(message),
            font=0,
            sender={"user_id": user},
        )

    async def deliver(self, event):
        await self.plugin.track_group_event(self.bot, event)
        if await self.plugin.chat.rule(self.bot, event, {}):
            await self.plugin.handle_group_message(self.bot, event)

    async def test_wrong_group_is_counted_without_reply_or_handling(self):
        await self.deliver(self.event(group=29999))
        counts = diagnostics.snapshot()
        self.assertEqual(counts["group_events"], 1)
        self.assertEqual(counts["mentioned_events"], 1)
        self.assertEqual(counts["ignored_group"], 1)
        self.assertEqual(counts["handled"], 0)
        self.bot.send.assert_not_awaited()

    async def test_matching_ping_counts_one_reply_and_duplicate_is_not_resent(self):
        event = self.event()
        event.message.pop(0)  # 适配器剥离 @ 后，仍使用 original_message 统计。
        await self.deliver(event)
        await self.deliver(event)
        counts = diagnostics.snapshot()
        self.assertEqual(counts["group_events"], 2)
        self.assertEqual(counts["mentioned_events"], 2)
        self.assertEqual(counts["handled"], 2)
        self.assertEqual(counts["replies_sent"], 1)
        self.assertEqual(counts["reply_errors"], 0)
        self.bot.send.assert_awaited_once()

    async def test_send_failure_is_counted_once_without_exception_content(self):
        self.bot.send.side_effect = RuntimeError("private-message-and-credentials")
        await self.deliver(self.event())
        counts = diagnostics.snapshot()
        self.assertEqual(counts["handled"], 1)
        self.assertEqual(counts["reply_errors"], 1)
        self.assertEqual(counts["replies_sent"], 0)
        self.assertNotIn("private-message-and-credentials", str(counts))
        self.assertTrue(all(type(value) is int for value in counts.values()))

    async def test_unmentioned_group_event_is_counted_without_triggering(self):
        await self.deliver(self.event(mention=False, group=29999))
        counts = diagnostics.snapshot()
        self.assertEqual(counts["group_events"], 1)
        self.assertEqual(sum(counts.values()), 1)
        self.bot.send.assert_not_awaited()

    async def test_self_and_wrong_account_have_separate_fixed_counters(self):
        await self.deliver(self.event(user=10000))
        self.plugin.set_service(
            ChatService(
                Settings(allowed_groups=frozenset({"20000"}), napcat_self_id="19999"),
                SimpleNamespace(),
            )
        )
        await self.deliver(self.event())
        counts = diagnostics.snapshot()
        self.assertEqual(counts["ignored_self"], 1)
        self.assertEqual(counts["ignored_account"], 1)
        self.assertEqual(counts["handled"], 0)
        self.bot.send.assert_not_awaited()

    async def test_non_send_handler_failure_is_counted_once(self):
        self.service.handle = AsyncMock(side_effect=RuntimeError("private-internal-error"))
        await self.deliver(self.event())
        counts = diagnostics.snapshot()
        self.assertEqual(counts["reply_errors"], 1)
        self.assertEqual(counts["replies_sent"], 0)
        self.bot.send.assert_not_awaited()

    async def test_private_messages_do_not_change_diagnostics(self):
        event = PrivateMessageEvent(
            time=0,
            self_id=10000,
            post_type="message",
            sub_type="friend",
            user_id=30000,
            message_id=1,
            message_type="private",
            message="/ping",
            raw_message="/ping",
            font=0,
            sender={"user_id": 30000},
        )
        await self.plugin.track_group_event(self.bot, event)
        self.assertTrue(all(value == 0 for value in diagnostics.snapshot().values()))
