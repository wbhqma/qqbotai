"""查找已归一化图片的候选作品页；不下载、转发或保存搜索结果图片。"""

import asyncio
from dataclasses import dataclass
import ipaddress
import json
import math
import re
import unicodedata
from urllib.parse import parse_qsl, unquote, urlsplit

import httpx

from app.config import Settings
from app.llm import ModelError

SEARCH_URL = "https://saucenao.com/search.php"
MAX_RESPONSE = 1024 * 1024
MAX_IMAGE = 490_000
MIN_SIMILARITY = 70


@dataclass(frozen=True, repr=False)
class _Candidate:
    similarity: float
    title: str
    author: str
    url: str


def _text(value: object, limit: int, key: str) -> str:
    if isinstance(value, list):
        value = ", ".join(item for item in value if isinstance(item, str))
    if not isinstance(value, str):
        return ""
    value = value.replace(key, "[已隐藏]") if key else value
    value = re.sub(r"(?i)\bhttps?://\S+", "", value)
    value = "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    return " ".join(value.split())[:limit]


def _public_source(value: object, key: str) -> str | None:
    if (not isinstance(value, str) or not value or len(value) > 400 or "\\" in value
            or any(char.isspace() or unicodedata.category(char).startswith("C") for char in value)):
        return None
    decoded = unquote(unquote(value))
    if key and (key in value or key in decoded):
        return None
    if any(unicodedata.category(char).startswith("C") for char in decoded):
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (parsed.scheme != "https" or not host or parsed.username or parsed.password
                or parsed.fragment or parsed.port not in (None, 443)):
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            ascii_host = host.encode("idna").decode("ascii")
            if (not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", ascii_host)
                    or "." not in ascii_host or ascii_host.rsplit(".", 1)[-1].isdigit()
                    or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
                           for label in ascii_host.split("."))
                    or host in ("localhost", "localhost.localdomain")
                    or host.endswith((".localhost", ".local", ".localdomain", ".internal", ".lan",
                                      ".home", ".invalid", ".test", ".onion"))):
                return None
        else:
            if not address.is_global:
                return None
        for name, _ in parse_qsl(parsed.query, keep_blank_values=True):
            normalized = unquote(name).casefold()
            if (any(term in normalized for term in
                    ("token", "key", "secret", "auth", "password", "credential", "signature"))
                    or normalized in ("sig", "pwd", "passwd", "session", "sessionid")):
                return None
        return value
    except (ValueError, UnicodeError):
        return None


def _status(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]{1,8}", value):
        return int(value)
    raise ValueError


class SauceNaoService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(25, connect=5), follow_redirects=False,
        )
        self.owns_client = client is None

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()

    async def _request(self, picture: bytes, key: str) -> dict:
        # multipart POST 已由 Sagiri 客户端源码验证；Key 不进入请求 URL。
        # hide=3 在 PicImageSearch 参数文档中表示只保留预期安全结果。
        request = httpx.Request("POST", SEARCH_URL, headers={"Accept": "application/json"},
                                data={"api_key": key, "output_type": "2", "numres": "5", "hide": "3"},
                                files={"file": ("image.jpg", picture, "image/jpeg")},
                                extensions={"timeout": httpx.Timeout(25, connect=5).as_dict()})
        try:
            async with asyncio.timeout(25):
                response = await self.client.send(request, auth=None, stream=True, follow_redirects=False)
                try:
                    if response.status_code in (401, 403):
                        raise ModelError("SauceNAO 暂时未接受连接，请管理员检查密钥与服务访问情况。")
                    if response.status_code == 429:
                        raise ModelError("SauceNAO 查询额度不足或请求过于频繁，请稍后再试。")
                    if response.status_code in (400, 413, 422):
                        raise ModelError("SauceNAO 未接受这张图片，请换一张清晰的普通图片。")
                    if response.status_code != 200:
                        raise ModelError("SauceNAO 搜图服务暂时不可用，请稍后再试。")
                    length = response.headers.get("content-length")
                    if length is not None and int(length) > MAX_RESPONSE:
                        raise ValueError
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE:
                            raise ValueError
                        body.extend(chunk)
                    payload = json.loads(body)
                    if not isinstance(payload, dict) or not isinstance(payload.get("header"), dict):
                        raise ValueError
                    status = _status(payload["header"].get("status"))
                    if status < 0:
                        header = payload["header"]
                        exhausted = any(
                            isinstance(header.get(name), (int, float)) and header[name] <= 0
                            for name in ("short_remaining", "long_remaining")
                        )
                        if exhausted:
                            raise ModelError("SauceNAO 查询额度不足或请求过于频繁，请稍后再试。")
                        raise ModelError("SauceNAO 未接受本次请求，请管理员检查密钥、额度与图片格式。")
                    if status > 0:
                        raise ModelError("SauceNAO 搜图服务暂时未完成查询，请稍后再试。")
                    if not isinstance(payload.get("results"), list):
                        raise ValueError
                    return payload
                finally:
                    await response.aclose()
        except (httpx.HTTPError, TimeoutError):
            raise ModelError("SauceNAO 搜图服务暂时无法连接，请稍后再试。") from None
        except (ValueError, TypeError, OverflowError):
            raise ModelError("SauceNAO 返回的数据不可用，请稍后再试。") from None

    def _candidates(self, payload: dict, key: str) -> list[_Candidate]:
        candidates = []
        for row in payload["results"]:
            if not isinstance(row, dict):
                continue
            header, data = row.get("header"), row.get("data")
            if not isinstance(header, dict) or not isinstance(data, dict):
                continue
            if header.get("hidden", 0) not in (0, "0", False, None):
                continue
            try:
                similarity = float(header.get("similarity"))
            except (ValueError, TypeError, OverflowError):
                continue
            if not math.isfinite(similarity) or not MIN_SIMILARITY <= similarity <= 100:
                continue
            url = None
            pixiv_id = data.get("pixiv_id")
            if type(pixiv_id) in (str, int) and re.fullmatch(r"[1-9][0-9]{0,19}", str(pixiv_id)):
                url = f"https://www.pixiv.net/artworks/{pixiv_id}"
            else:
                urls = data.get("ext_urls", [])
                if isinstance(urls, list):
                    url = next((valid for item in urls
                                if (valid := _public_source(item, key)) is not None), None)
            if not url:
                continue
            title = next((_text(data.get(name), 90, key)
                          for name in ("title", "material", "jp_name", "eng_name")
                          if _text(data.get(name), 90, key)), "作品页")
            author = next((_text(data.get(name), 80, key)
                           for name in ("member_name", "creator", "author", "author_name", "artist",
                                        "twitter_user_handle", "user_name")
                           if _text(data.get(name), 80, key)), "未提供")
            candidates.append(_Candidate(similarity, title, author, url))
        candidates.sort(key=lambda candidate: candidate.similarity, reverse=True)
        unique = []
        seen = set()
        for candidate in candidates:
            if candidate.url in seen:
                continue
            unique.append(candidate)
            seen.add(candidate.url)
            if len(unique) == 3:
                break
        return unique

    async def search(self, picture: bytes) -> str:
        key = self.settings.saucenao_api_key.strip()
        if not key or any(unicodedata.category(char).startswith("C") for char in key):
            raise ModelError("以图搜源尚未配置，请管理员在本机填写 SAUCENAO_API_KEY。")
        if not isinstance(picture, bytes) or not picture or len(picture) > MAX_IMAGE:
            raise ModelError("搜图需要已压缩的 JPEG 图片，请重新发送较小的图片。")
        payload = await self._request(picture, key)
        candidates = self._candidates(payload, key)
        if not candidates:
            return "没有找到相似度足够、可展示的作品页候选。可以换更完整清晰的图片；搜索仅覆盖服务已收录内容。"
        lines = ["候选出处（相似度是图像匹配分数，不能认证原作者；页面署名来自检索结果）："]
        for number, candidate in enumerate(candidates, 1):
            lines.append(f"{number}. {candidate.title}\n页面署名：{candidate.author}\n"
                         f"相似度：{candidate.similarity:.1f}%\n{candidate.url}")
        return "\n\n".join(lines)
