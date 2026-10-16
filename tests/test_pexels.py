import io
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from app.config import Settings
from app.images import MAX_DOWNLOAD
from app.llm import ModelError
from app.pexels import CACHE_LIMIT, PexelsService, PhotoResult


KEY = "pexels-local-test-key"
SOURCE = "https://www.pexels.com/photo/blue-whale-12345/"
CDN = "https://images.pexels.com/photos/12345/pexels-photo-12345.jpeg?auto=compress&cs=tinysrgb&w=640"


def picture():
    output = io.BytesIO()
    image = Image.new("RGB", (32, 24), "blue")
    exif = Image.Exif()
    exif[0x010E] = "private-exif-test"
    image.save(output, "JPEG", exif=exif)
    return output.getvalue()


def photo(url=CDN, source=SOURCE):
    return {"photos": [{"alt": "蓝色鲸鱼", "photographer": "Test Photographer",
                         "url": source, "src": {"large": url}}]}


class PexelsTests(unittest.IsolatedAsyncioTestCase):
    def settings(self):
        return Settings(pexels_api_key=KEY)

    async def test_chinese_query_auth_attribution_and_exif_removal(self):
        requests = []

        def respond(request):
            requests.append(request)
            if request.url.host == "api.pexels.com":
                self.assertEqual(request.method, "GET")
                self.assertEqual(request.url.path, "/v1/search")
                self.assertEqual(request.url.params["query"], "蓝色 鲸鱼")
                self.assertEqual(request.url.params["per_page"], "1")
                self.assertEqual(request.url.params["locale"], "zh-CN")
                self.assertEqual(request.headers["Authorization"], KEY)
                self.assertNotIn(KEY, str(request.url))
                self.assertFalse(request.content)
                return httpx.Response(200, json=photo())
            self.assertEqual(request.url.host, "images.pexels.com")
            for header in ("Authorization", "Cookie", "X-API-Key"):
                self.assertNotIn(header, request.headers)
            return httpx.Response(200, content=picture())

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond), auth=("private-client-user", "private-pass"),
            headers={"Authorization": "unrelated-private-key", "X-API-Key": "unrelated-key"},
            cookies={"private-cookie": "hidden"}, follow_redirects=True,
        ) as client:
            service = PexelsService(self.settings(), client)
            result = await service.search("蓝色 鲸鱼")
            self.assertIsInstance(result, PhotoResult)
            self.assertIn("蓝色鲸鱼", result.caption)
            self.assertIn("Test Photographer / Pexels", result.caption)
            self.assertIn(SOURCE, result.caption)
            self.assertNotIn(KEY, repr(result))
            self.assertNotIn(b"private-exif-test", result.image)
            with Image.open(io.BytesIO(result.image)) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertFalse(image.getexif())
            await service.close()
            self.assertFalse(client.is_closed)
        self.assertEqual(len(requests), 2)

    async def test_missing_key_and_invalid_queries_never_connect(self):
        def respond(request):
            self.fail("invalid input must not access the network")

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            missing = PexelsService(Settings(), client)
            with self.assertRaisesRegex(ModelError, "PEXELS_API_KEY"):
                await missing.search("鲸鱼")
            service = PexelsService(self.settings(), client)
            for query in ("", "   ", "x" * 101, "鲸鱼\n", "鲸鱼\x00", "鲸鱼\u202e", None):
                with self.subTest(query=repr(query)), self.assertRaises(ModelError):
                    await service.search(query)

    async def test_bad_cdn_urls_fall_back_to_caption_without_fetch(self):
        bad_urls = (
            "http://images.pexels.com/photos/1/a.jpg", "file:///private.jpg",
            "https://images.pexels.com.evil.example/photos/1/a.jpg",
            "https://user:password@images.pexels.com/photos/1/a.jpg",
            "https://images.pexels.com:8443/photos/1/a.jpg",
            "https://images.pexels.com/photos/1/a.jpg#fragment",
            "https://images.pexels.com/private.jpg",
            "https://images.pexels.com/photos/../a.jpg",
            "https://images.pexels.com/photos/1/a.jpg?token=hidden",
            "https://images.pexels.com/photos/1/a.jpg?api_key=hidden",
            "https://images.pexels.com/photos/1/a.jpg?secret=hidden",
            "https://images.pexels.com/photos/1/a.jpg?rkey=hidden",
            "https://images.pexels.com/photos/1/a.jpg?w=1%0a2",
            "https://images.pexels.com/photos/1/a.jpg?w=100&w=200",
            "https://images.pexels.com/pho\ntos/1/a.jpg",
        )
        for url in bad_urls:
            calls = []

            def respond(request):
                calls.append(request)
                self.assertEqual(request.url.host, "api.pexels.com")
                return httpx.Response(200, json=photo(url=url))

            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                result = await PexelsService(self.settings(), client).search("鲸鱼")
            with self.subTest(url=url):
                self.assertIsNone(result.image)
                self.assertIn(SOURCE, result.caption)
                self.assertNotIn("hidden", result.caption)
                self.assertEqual(len(calls), 1)

    async def test_bad_source_urls_are_never_displayed(self):
        for source in ("https://evil.example/photo/1/", SOURCE + "?token=hidden",
                       "https://user:password@www.pexels.com/photo/1/", "javascript:alert(1)"):
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=photo(source=source)))) as client:
                with self.assertRaises(ModelError) as caught:
                    await PexelsService(self.settings(), client).search("鲸鱼")
                self.assertNotIn(source, str(caught.exception))

    async def test_redirect_oversize_bad_image_and_network_fall_back(self):
        for failure in ("redirect", "length", "stream", "bad-image", "network"):
            calls = []

            def respond(request):
                calls.append(request)
                if request.url.host == "api.pexels.com":
                    return httpx.Response(200, json=photo())
                if failure == "redirect":
                    return httpx.Response(302, headers={"Location": "https://private.example/secret"})
                if failure == "length":
                    return httpx.Response(200, headers={"content-length": str(MAX_DOWNLOAD + 1)})
                if failure == "stream":
                    return httpx.Response(200, content=b"x" * (MAX_DOWNLOAD + 1))
                if failure == "network":
                    raise httpx.ConnectError("private error with token", request=request)
                return httpx.Response(200, content=b"private invalid image")

            async with httpx.AsyncClient(transport=httpx.MockTransport(respond), follow_redirects=True) as client:
                result = await PexelsService(self.settings(), client).search("鲸鱼")
            with self.subTest(failure=failure):
                self.assertIsNone(result.image)
                self.assertIn(SOURCE, result.caption)
                self.assertNotIn("private", result.caption)
                self.assertEqual(len(calls), 2)

    async def test_api_errors_are_fixed_messages_without_raw_responses(self):
        for status in (301, 401, 403, 429, 500):
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(status, text="private-error-body",
                                                   headers={"Location": "https://private.example/"})),
                    follow_redirects=True) as client:
                with self.assertRaises(ModelError) as caught:
                    await PexelsService(self.settings(), client).search("鲸鱼")
                self.assertNotIn("private", str(caught.exception))
                self.assertNotIn(KEY, str(caught.exception))

    async def test_invalid_api_json_shapes_and_empty_results_are_safe(self):
        cases = ([], {}, {"photos": "private-response"}, {"photos": [None]},
                 {"photos": []}, {"photos": [{"url": SOURCE, "src": []}]})
        for payload in cases:
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=payload))) as client:
                with self.assertRaises(ModelError) as caught:
                    await PexelsService(self.settings(), client).search("鲸鱼")
                self.assertNotIn("private-response", str(caught.exception))
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"not-json-private"))) as client:
            with self.assertRaises(ModelError) as caught:
                await PexelsService(self.settings(), client).search("鲸鱼")
            self.assertNotIn("not-json-private", str(caught.exception))

    async def test_api_network_error_and_large_response_are_safe(self):
        def network_error(request):
            raise httpx.ReadTimeout("private-network-detail", request=request)

        for respond in (network_error, lambda request: httpx.Response(
                200, content=b"x" * (1024 * 1024 + 1))):
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                with self.assertRaises(ModelError) as caught:
                    await PexelsService(self.settings(), client).search("鲸鱼")
                self.assertNotIn("private-network-detail", str(caught.exception))

    async def test_metadata_cache_is_bounded_expires_and_never_caches_images(self):
        api_calls = []
        image_calls = []

        def respond(request):
            if request.url.host == "api.pexels.com":
                api_calls.append(request)
                return httpx.Response(200, json=photo())
            image_calls.append(request)
            return httpx.Response(200, content=picture())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            service = PexelsService(self.settings(), client)
            await service.search("鲸鱼")
            await service.search("鲸鱼")
            self.assertEqual(len(api_calls), 1)
            self.assertEqual(len(image_calls), 2)
            metadata = service._cache["鲸鱼"][1]
            self.assertFalse(hasattr(metadata, "image"))
            service._cache["鲸鱼"] = (0, metadata)
            await service.search("鲸鱼")
            self.assertEqual(len(api_calls), 2)
            with patch("app.pexels.normalize_image", return_value=b"jpeg"):
                for number in range(CACHE_LIMIT + 1):
                    await service.search(f"鲸鱼{number}")
            self.assertEqual(len(service._cache), CACHE_LIMIT)
            self.assertNotIn("鲸鱼0", service._cache)
            await service.close()
            self.assertFalse(service._cache)

    async def test_owned_client_is_closed(self):
        service = PexelsService(self.settings())
        await service.close()
        self.assertTrue(service.client.is_closed)
