"""按关键词查询 Pexels；不接收群图片，不保存查询或图片。"""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
import json
import re
import time
import unicodedata
from urllib.parse import parse_qsl, urlsplit

import httpx

from app.config import Settings
from app.images import MAX_DOWNLOAD, normalize_image
from app.llm import ModelError

SEARCH_URL = "https://api.pexels.com/v1/search"
CACHE_LIMIT = 64
CACHE_TTL = 24 * 60 * 60
MAX_API_RESPONSE = 1024 * 1024
IMAGE_PARAMETERS = frozenset({"auto", "cs", "w", "h", "fit", "crop", "dpr", "q", "fm"})


@dataclass(frozen=True)
class PhotoResult:
    caption: str = field(repr=False)
    image: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True, repr=False)
class _PhotoMetadata:
    caption: str
    image_url: str | None


def _split_url(value: object):
    if (not isinstance(value, str) or not value or len(value) > 2048
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.fragment):
            return None
        return parsed
    except ValueError:
        return None


def _source_url(value: object) -> str | None:
    parsed = _split_url(value)
    if (parsed is None or parsed.hostname != "www.pexels.com" or parsed.query
            or not re.fullmatch(r"/photo/[a-zA-Z0-9-]*[0-9]/?", parsed.path)):
        return None
    return str(value)


def _image_url(value: object) -> str | None:
    parsed = _split_url(value)
    if (parsed is None or parsed.hostname != "images.pexels.com"
            or not re.fullmatch(r"/photos/[0-9]+/[a-zA-Z0-9_.-]+", parsed.path)):
        return None
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    if len(pairs) > len(IMAGE_PARAMETERS) or len({name for name, _ in pairs}) != len(pairs):
        return None
    for name, value_part in pairs:
        if name not in IMAGE_PARAMETERS or not re.fullmatch(r"[a-zA-Z0-9.,:_-]{1,80}", value_part):
            return None
    return str(value)


def _text(value: object, default: str, limit: int, key: str) -> str:
    text = value if isinstance(value, str) else default
    if key:
        text = text.replace(key, "[已隐藏]")
    text = "".join(char for char in text if not unicodedata.category(char).startswith("C"))
    return " ".join(text.split())[:limit] or default


class PexelsService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(15, connect=5), follow_redirects=False,
        )
        self.owns_client = client is None
        self._cache: OrderedDict[str, tuple[float, _PhotoMetadata]] = OrderedDict()

    async def close(self) -> None:
        self._cache.clear()
        if self.owns_client:
            await self.client.aclose()

    async def _read(self, url: str, *, headers: dict[str, str], limit: int,
                    params: dict | None = None) -> tuple[int, bytes]:
        # Request 不继承共享客户端的默认密钥、Cookie 或 auth；CDN 只收到 Accept。
        request = httpx.Request("GET", url, params=params, headers=headers, extensions={
            "timeout": httpx.Timeout(15, connect=5).as_dict(),
        })
        response = await self.client.send(request, stream=True, auth=None, follow_redirects=False)
        try:
            if response.status_code != 200:
                return response.status_code, b""
            length = response.headers.get("content-length")
            if length is not None and int(length) > limit:
                raise ValueError("response too large")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                if len(data) + len(chunk) > limit:
                    raise ValueError("response too large")
                data.extend(chunk)
            return response.status_code, bytes(data)
        finally:
            await response.aclose()

    async def _metadata(self, query: str, key: str) -> _PhotoMetadata:
        now = time.monotonic()
        for cached_query, (expires_at, _) in list(self._cache.items()):
            if expires_at <= now:
                del self._cache[cached_query]
        cached = self._cache.get(query)
        if cached is not None:
            self._cache.move_to_end(query)
            return cached[1]
        try:
            async with asyncio.timeout(20):
                status, body = await self._read(
                    SEARCH_URL, headers={"Authorization": key, "Accept": "application/json"},
                    params={"query": query, "per_page": 1, "locale": "zh-CN"},
                    limit=MAX_API_RESPONSE,
                )
            if status in (401, 403):
                raise ModelError("Pexels 鉴权失败，请管理员检查 PEXELS_API_KEY。")
            if status == 429:
                raise ModelError("Pexels 请求过于频繁或额度已用完，请稍后再试。")
            if status != 200:
                raise ModelError("Pexels 搜图服务暂时不可用，请稍后再试。")
            data = json.loads(body)
            if not isinstance(data, dict) or not isinstance(data.get("photos"), list):
                raise ValueError
            if not data["photos"]:
                raise ModelError("没有找到合适的 Pexels 图片，试试更具体的关键词。")
            photo = data["photos"][0]
            if not isinstance(photo, dict):
                raise ValueError
            source = _source_url(photo.get("url"))
            if source is None:
                raise ValueError
            alt = _text(photo.get("alt"), "Pexels 图片", 100, key)
            photographer = _text(photo.get("photographer"), "未知摄影师", 80, key)
            caption = f"{alt}\n摄影师：{photographer} / Pexels\n{source}"
            src = photo.get("src", {})
            if not isinstance(src, dict):
                raise ValueError
            picture = next((valid for name in ("large", "medium", "original")
                            if (valid := _image_url(src.get(name))) is not None), None)
            metadata = _PhotoMetadata(caption, picture)
        except (httpx.HTTPError, TimeoutError):
            raise ModelError("Pexels 搜图服务暂时无法连接，请稍后再试。") from None
        except (ValueError, TypeError, KeyError, OverflowError):
            raise ModelError("Pexels 未返回可用图片信息，请稍后再试。") from None
        self._cache[query] = (time.monotonic() + CACHE_TTL, metadata)
        self._cache.move_to_end(query)
        while len(self._cache) > CACHE_LIMIT:
            self._cache.popitem(last=False)
        return metadata

    async def search(self, query: str) -> PhotoResult:
        if (not isinstance(query, str) or len(query) > 100 or not query.strip()
                or any(unicodedata.category(char).startswith("C") for char in query)):
            raise ModelError("请输入 1—100 字的图片关键词，不要包含控制字符。")
        query = query.strip()
        key = self.settings.pexels_api_key.strip()
        if not key or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise ModelError("找图尚未配置，请管理员在本机填写 PEXELS_API_KEY。")
        metadata = await self._metadata(query, key)
        if metadata.image_url is None:
            return PhotoResult(metadata.caption)
        try:
            async with asyncio.timeout(25):
                status, raw = await self._read(
                    metadata.image_url, headers={"Accept": "image/*"}, limit=MAX_DOWNLOAD,
                )
                if status != 200:
                    return PhotoResult(metadata.caption)
                image = await asyncio.to_thread(normalize_image, raw)
            return PhotoResult(metadata.caption, image)
        except (httpx.HTTPError, ModelError, ValueError, TimeoutError, OverflowError):
            return PhotoResult(metadata.caption)
