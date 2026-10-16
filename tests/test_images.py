import io
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image

from app.config import Settings
from app.images import ImageService, MAX_DOWNLOAD, normalize_image, validate_image_url
from app.llm import ModelError


def sample_image():
    output = io.BytesIO()
    Image.new("RGB", (32, 24), "blue").save(output, "PNG")
    return output.getvalue()


class ImageTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, provider="compatible"):
        return Settings(
            vision_provider=provider,
            vision_base_url="https://vision.example/v1",
            vision_model="test-vision",
            vision_api_key="test-vision-key",
            serpapi_api_key="test-search-key",
        )

    def test_only_qq_https_image_attachments_are_downloadable(self):
        validate_image_url("https://multimedia.nt.qq.com/download?example=1")
        validate_image_url("https://multimedia.nt.qq.com.cn/download?example=1")
        validate_image_url("https://gchat.qpic.cn/image")
        for url in (
            "http://gchat.qpic.cn/a",
            "https://127.0.0.1/a",
            "file:///private.jpg",
            "https://gchat.qpic.cn.evil.example/a",
            "https://user:password@gchat.qpic.cn/a",
            "https://gchat.qpic.cn:8443/a",
            "https://example.com/a",
        ):
            with self.subTest(url=url), self.assertRaises(ModelError):
                validate_image_url(url)

    def test_image_validation_compression_and_size_limit(self):
        data = normalize_image(sample_image(), for_search=True)
        self.assertLess(len(data), 500_000)
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertFalse(image.getexif())
        for bad in (b"not an image", b"x" * (MAX_DOWNLOAD + 1)):
            with self.assertRaises(ModelError):
                normalize_image(bad)

    def test_private_exif_is_removed_before_upload(self):
        source = io.BytesIO()
        image = Image.new("RGB", (32, 24), "blue")
        exif = Image.Exif()
        exif[0x010E] = "test-private-metadata"
        image.save(source, "JPEG", exif=exif)
        clean = normalize_image(source.getvalue())
        self.assertNotIn(b"test-private-metadata", clean)
        with Image.open(io.BytesIO(clean)) as result:
            self.assertFalse(result.getexif())

    async def test_all_vision_protocols_send_image_and_parse_text(self):
        for provider in ("compatible", "ollama", "openai", "anthropic", "gemini"):
            requests = []

            def respond(request):
                requests.append(request)
                payload = {
                    "openai": {
                        "output": [
                            {
                                "type": "message",
                                "content": [{"type": "output_text", "text": "蓝色方块"}],
                            }
                        ]
                    },
                    "anthropic": {"content": [{"type": "text", "text": "蓝色方块"}]},
                    "gemini": {"candidates": [{"content": {"parts": [{"text": "蓝色方块"}]}}]},
                }.get(provider, {"choices": [{"message": {"content": "蓝色方块"}}]})
                return httpx.Response(200, json=payload)

            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                service = ImageService(self.settings(provider), client)
                self.assertEqual(
                    await service.analyze(normalize_image(sample_image()), "图片是什么"), "蓝色方块"
                )
            payload = json.loads(requests[0].content)
            serialized = json.dumps(payload)
            self.assertIn("/9j/", serialized)
            if provider == "openai":
                self.assertFalse(payload["store"])
            self.assertNotIn("test-search-key", serialized)

    async def test_reverse_search_uploads_bytes_filters_results_and_keeps_safe_search(self):
        requests = []

        def respond(request):
            requests.append(request)
            if request.url.path == "/image":
                self.assertIn(b"image.jpg", request.content)
                self.assertNotIn(b"qpic.cn", request.content)
                return httpx.Response(200, json={"image_id": "test-image-id"})
            self.assertEqual(request.url.params["image_id"], "test-image-id")
            self.assertEqual(request.url.params["safe"], "active")
            return httpx.Response(
                200,
                json={
                    "visual_matches": [
                        {"title": "坏链接", "link": "javascript:example"},
                        {
                            "title": "不应展示凭证",
                            "link": "https://example.com/?token=test-private",
                        },
                        {"title": "蓝色方块", "link": "https://example.com/source"},
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            service = ImageService(self.settings(), client)
            answer = await service.search(normalize_image(sample_image(), for_search=True))
        self.assertEqual(len(requests), 2)
        self.assertIn("https://example.com/source", answer)
        self.assertNotIn("test-private", answer)
        self.assertNotIn("javascript", answer)

    async def test_unconfigured_features_do_not_read_or_upload_images(self):
        service = ImageService(Settings())
        self.addAsyncCleanup(service.close)
        service.download = AsyncMock()
        for mode in ("search", "analyze"):
            with self.assertRaises(ModelError):
                await service.process("https://gchat.qpic.cn/a", mode)
        service.download.assert_not_awaited()

    async def test_redirect_oversize_and_service_errors_are_safe(self):
        for status, body in ((302, b""), (200, b"x" * (MAX_DOWNLOAD + 1))):

            def respond(request):
                return httpx.Response(
                    status, content=body, headers={"Location": "http://127.0.0.1/private"}
                )

            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                service = ImageService(self.settings(), client)
                with self.assertRaises(ModelError):
                    await service.download("https://gchat.qpic.cn/a")
        for status in (401, 402, 429, 500):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(status, json={"error": "test-private-response"})
                )
            ) as client:
                service = ImageService(self.settings(), client)
                with self.assertRaises(ModelError) as error:
                    await service.analyze(normalize_image(sample_image()), "test")
                self.assertNotIn("test-private-response", str(error.exception))
