import contextlib
import io
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import nonebot
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from PIL import Image

from app.chat import ChatService
from app.config import Settings
from app.images import ImageService
from app.llm import ModelError


class ImageSourceDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_saucenao_uses_its_own_provider_without_also_calling_serpapi(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: self.fail("No SerpApi request expected"))) as client:
            service = ImageService(Settings(saucenao_api_key="test-source-key", serpapi_api_key="test-serp-key"), client)
            with patch("app.images.SauceNaoService") as constructor:
                constructor.return_value.search = AsyncMock(return_value="候选出处")
                self.assertEqual(await service.search(b"test-jpeg"), "候选出处")
                constructor.assert_called_once_with(service.settings, client)
                constructor.return_value.search.assert_awaited_once_with(b"test-jpeg")

    async def test_source_upload_receives_only_normalized_jpeg_without_qq_url_or_exif(self):
        source = io.BytesIO()
        image = Image.new("RGB", (32, 24), "blue")
        metadata = Image.Exif()
        metadata[0x010E] = "test-private-camera-data"
        image.save(source, "JPEG", exif=metadata)
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=source.getvalue()))) as client:
            service = ImageService(Settings(saucenao_api_key="test-source-key"), client)
            with patch("app.images.SauceNaoService") as constructor:
                constructor.return_value.search = AsyncMock(return_value="候选出处")
                await service.process("https://gchat.qpic.cn/image?rkey=test-private-link", "search")
                picture = constructor.return_value.search.call_args.args[0]
                self.assertIsInstance(picture, bytes)
                self.assertNotIn(b"test-private-camera-data", picture)
                self.assertNotIn(b"qpic.cn", picture)
                with Image.open(io.BytesIO(picture)) as clean:
                    self.assertEqual(clean.format, "JPEG")

    async def test_unconfigured_source_search_never_downloads(self):
        service = ImageService(Settings())
        self.addAsyncCleanup(service.close)
        service.download = AsyncMock()
        with self.assertRaises(ModelError):
            await service.process("https://gchat.qpic.cn/image", "search")
        service.download.assert_not_awaited()


class ImageSourceCommandTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder):
            nonebot.init(driver="~none", log_level="WARNING")
        cls.plugin = (nonebot.get_plugin("qq_chat") or nonebot.load_plugin("plugins.qq_chat")).module

    async def asyncSetUp(self):
        self.bot = Bot(SimpleNamespace(), "10000")
        self.bot.send = AsyncMock()
        self.service = ChatService(Settings(allowed_groups=frozenset({"20000"}), cooldown_seconds=0), SimpleNamespace())
        self.plugin.set_service(self.service)
        self.images = SimpleNamespace(process=AsyncMock(return_value="候选作品页面"))
        self.plugin.set_images(self.images)

    def event(self, command, picture=True):
        message = Message(MessageSegment.at("10000")) + MessageSegment.text(command)
        if picture:
            message += MessageSegment("image", {"file": "test.jpg", "url": "https://gchat.qpic.cn/image"})
        return GroupMessageEvent(time=0, self_id=10000, post_type="message", sub_type="normal",
                                 user_id=30000, group_id=20000, message_id=1, message_type="group",
                                 message=message, raw_message=str(message), font=0, sender={"user_id": 30000})

    async def test_explicit_source_commands_use_image_search_and_do_not_store_result(self):
        for command in ("/查出处", "/出处", "/搜图"):
            self.service.seen.clear()
            self.images.process.reset_mock()
            await self.plugin.handle_group_message(self.bot, self.event(command))
            self.images.process.assert_awaited_once_with("https://gchat.qpic.cn/image", "search", command)
            self.assertEqual(self.service.sessions[("10000", "20000", "30000")].messages, [])

    async def test_source_command_without_picture_requests_one_instead_of_guessing(self):
        await self.plugin.handle_group_message(self.bot, self.event("/查出处", picture=False))
        self.images.process.assert_not_awaited()
        self.assertIn("一张图片", self.bot.send.call_args.args[1].data["text"])
