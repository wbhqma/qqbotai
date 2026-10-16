import io
import unittest

import httpx
from PIL import Image

from app.config import Settings
from app.images import normalize_image
from app.llm import ModelError
from app.saucenao import MAX_IMAGE, MAX_RESPONSE, SauceNaoService


KEY = "saucenao-local-test-key"


def picture():
    output = io.BytesIO()
    image = Image.new("RGB", (32, 24), "blue")
    exif = Image.Exif()
    exif[0x010E] = "private-test-metadata"
    image.save(output, "JPEG", exif=exif)
    return normalize_image(output.getvalue(), for_search=True)


def result(score="93.25", hidden=0, **data):
    return {"header": {"similarity": score, "hidden": hidden, "index_id": 5,
                       "thumbnail": "https://private.example/thumbnail.jpg"},
            "data": {"title": "蓝色鲸鱼", "member_name": "测试画师", "pixiv_id": "12345678", **data}}


def payload(results=None, status=0, **header):
    return {"header": {"status": status, "short_remaining": 3, "long_remaining": 99, **header},
            "results": [result()] if results is None else results}


class SauceNaoTests(unittest.IsolatedAsyncioTestCase):
    def settings(self):
        return Settings(saucenao_api_key=KEY)

    async def test_multipart_post_only_normalized_image_and_own_key(self):
        requests = []
        clean = picture()

        def respond(request):
            requests.append(request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), "https://saucenao.com/search.php")
            for name in ("Authorization", "Cookie", "X-API-Key"):
                self.assertNotIn(name, request.headers)
            self.assertIn("multipart/form-data; boundary=", request.headers["Content-Type"])
            self.assertIn(b'name="api_key"', request.content)
            self.assertIn(KEY.encode(), request.content)
            for name, value in (("output_type", "2"), ("numres", "5"), ("hide", "3")):
                self.assertIn(f'name="{name}"\r\n\r\n{value}\r\n'.encode(), request.content)
            self.assertIn(b'name="file"; filename="image.jpg"', request.content)
            self.assertIn(b"Content-Type: image/jpeg", request.content)
            self.assertIn(clean, request.content)
            for private in (b"private-test-metadata", b"qpic.cn", b"group_id", b"user_id", b"other-private-key"):
                self.assertNotIn(private, request.content)
            return httpx.Response(200, json=payload())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond), auth=("user", "password"),
                                     headers={"Authorization": "other-private-key", "X-API-Key": "other"},
                                     cookies={"private-cookie": "hidden"}) as client:
            service = SauceNaoService(self.settings(), client)
            answer = await service.search(clean)
            self.assertIn("不能认证原作者", answer)
            self.assertIn("测试画师", answer)
            self.assertIn("93.2%", answer)
            self.assertIn("https://www.pixiv.net/artworks/12345678", answer)
            self.assertNotIn("thumbnail", answer)
            self.assertEqual(len(requests), 1)
            await service.close()
            self.assertFalse(client.is_closed)

    async def test_missing_key_or_invalid_picture_never_connects(self):
        def unexpected(request):
            self.fail("invalid input must not use the network")

        async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
            with self.assertRaisesRegex(ModelError, "SAUCENAO_API_KEY"):
                await SauceNaoService(Settings(), client).search(picture())
            service = SauceNaoService(self.settings(), client)
            for invalid in (b"", None, "image", b"x" * (MAX_IMAGE + 1)):
                with self.subTest(value=type(invalid).__name__), self.assertRaises(ModelError):
                    await service.search(invalid)

    async def test_low_hidden_nonfinite_and_malformed_results_are_filtered(self):
        rows = [None, {}, {"header": [], "data": {}}, result(score="69.99"), result(score="NaN"),
                result(score="inf"), result(score="-inf"), result(score="101"), result(score="-1"),
                result(score=None), result(hidden=1), result(hidden="1"), result(hidden="3")]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
                200, json=payload(results=rows)))) as client:
            answer = await SauceNaoService(self.settings(), client).search(picture())
        self.assertIn("没有找到", answer)
        self.assertNotIn("12345678", answer)
        self.assertNotIn("测试画师", answer)

    async def test_results_sorted_deduplicated_and_limited_to_three(self):
        rows = [result(score="70", pixiv_id="1"), result(score="90", pixiv_id="2"),
                result(score="91", pixiv_id="2"), result(score="85", pixiv_id="3"),
                result(score="95", pixiv_id="4")]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
                200, json=payload(results=rows)))) as client:
            answer = await SauceNaoService(self.settings(), client).search(picture())
        self.assertEqual(answer.count("https://www.pixiv.net/artworks/"), 3)
        self.assertLess(answer.index("/artworks/4"), answer.index("/artworks/2"))
        self.assertLess(answer.index("/artworks/2"), answer.index("/artworks/3"))
        self.assertNotIn("/artworks/1", answer)

    async def test_external_source_urls_are_checked_and_never_fetched(self):
        bad_urls = (
            "http://example.com/work", "https://127.0.0.1/", "https://[::1]/",
            "https://192.168.1.1/", "https://169.254.169.254/", "https://intranet.local/",
            "https://user:password@example.com/", "https://example.com:8443/",
            "https://example.com/#private", "https://example.com/?token=hidden",
            "https://example.com/?api_key=hidden", "https://example.com/?rkey=hidden",
            "https://example.com/?X-Amz-Credential=hidden", "https://example.com/%0a",
            "https://example.com/" + KEY, "file:///private", "javascript:alert(1)",
        )
        rows = [result(pixiv_id=None, ext_urls=[url]) for url in bad_urls]
        rows.append(result(pixiv_id=None, ext_urls=["https://example.org/artwork/1"],
                           member_name="", creator=["画师甲", "画师乙"]))
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json=payload(results=rows))

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            answer = await SauceNaoService(self.settings(), client).search(picture())
        self.assertEqual(len(requests), 1)
        self.assertIn("https://example.org/artwork/1", answer)
        self.assertIn("画师甲, 画师乙", answer)
        self.assertNotIn("hidden", answer)
        self.assertNotIn(KEY, answer)
        self.assertNotIn("127.0.0.1", answer)

    async def test_pixiv_ids_are_digits_only_and_text_does_not_reflect_key(self):
        rows = [result(pixiv_id="bad-id", ext_urls=[]), result(pixiv_id=True, ext_urls=[]),
                result(pixiv_id="12345678?token=secret", ext_urls=[]),
                result(pixiv_id=12345, title=KEY + " " + "题" * 500,
                       member_name=KEY + " " + "名" * 500)]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
                200, json=payload(results=rows)))) as client:
            answer = await SauceNaoService(self.settings(), client).search(picture())
        self.assertIn("https://www.pixiv.net/artworks/12345", answer)
        self.assertNotIn(KEY, answer)
        self.assertNotIn("token=", answer)
        self.assertLess(len(answer), 600)

    async def test_http_api_errors_and_quota_use_fixed_safe_messages(self):
        for status in (302, 400, 401, 403, 413, 422, 429, 500):
            calls = []

            def respond(request):
                calls.append(request)
                return httpx.Response(status, text="private-response-" + KEY,
                                      headers={"Location": "https://private.example/"})

            async with httpx.AsyncClient(transport=httpx.MockTransport(respond), follow_redirects=True) as client:
                with self.subTest(status=status), self.assertRaises(ModelError) as caught:
                    await SauceNaoService(self.settings(), client).search(picture())
                self.assertNotIn(KEY, str(caught.exception))
                self.assertNotIn("private-response", str(caught.exception))
                self.assertEqual(len(calls), 1)
        for header in ({"status": -1}, {"status": -2, "short_remaining": 0},
                       {"status": -2, "long_remaining": 0}, {"status": 1}):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
                    200, json=payload(**header, message="private-" + KEY)))) as client:
                with self.assertRaises(ModelError) as caught:
                    await SauceNaoService(self.settings(), client).search(picture())
                self.assertNotIn("private", str(caught.exception))
                self.assertNotIn(KEY, str(caught.exception))

    async def test_network_shape_and_size_failures_do_not_expose_responses(self):
        def network_error(request):
            raise httpx.ReadTimeout("private-network-" + KEY, request=request)

        responders = (
            network_error,
            lambda request: httpx.Response(200, text="private-not-json"),
            lambda request: httpx.Response(200, json=[]),
            lambda request: httpx.Response(200, json={"header": {}}),
            lambda request: httpx.Response(200, json=payload(status=True)),
            lambda request: httpx.Response(200, json=payload(results="private")),
            lambda request: httpx.Response(200, content=b"x" * (MAX_RESPONSE + 1)),
            lambda request: httpx.Response(200, headers={"Content-Length": str(MAX_RESPONSE + 1)}),
        )
        for respond in responders:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                with self.assertRaises(ModelError) as caught:
                    await SauceNaoService(self.settings(), client).search(picture())
                self.assertNotIn("private", str(caught.exception))
                self.assertNotIn(KEY, str(caught.exception))

    async def test_valid_empty_search_returns_explanation_and_owned_client_closes(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
                200, json=payload(results=[])))) as client:
            answer = await SauceNaoService(self.settings(), client).search(picture())
            self.assertIn("搜索仅覆盖", answer)
        service = SauceNaoService(self.settings())
        await service.close()
        self.assertTrue(service.client.is_closed)
