import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote, urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOT_NAME = "哦鲸鲸"
LLM_DEFAULTS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-flash"),
    "compatible": ("", ""),
    "ollama": ("http://localhost:11434/v1", ""),
    "openai": ("https://api.openai.com/v1", ""),
    "anthropic": ("https://api.anthropic.com/v1", ""),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta", ""),
}
DEEPSEEK_URLS = frozenset({
    "https://api.deepseek.com", "https://api.deepseek.com/v1",
    "https://api.deepseek.com/chat/completions", "https://api.deepseek.com/v1/chat/completions",
})
RESERVED_MODEL_FIELDS = frozenset({
    "model", "messages", "input", "instructions", "system", "contents",
    "stream", "store", "max_tokens", "max_completion_tokens", "max_output_tokens",
})


def napcat_connection(values: Mapping[str, str]) -> tuple[str, int]:
    """两端共用连接字段的解析规则，调用方先按相同优先级加载环境。"""
    token = values.get("ONEBOT_ACCESS_TOKEN", "").strip()
    if any(ord(char) < 32 for char in token):
        raise ValueError("OneBot Token 不能包含控制字符。")
    try:
        port = int(values.get("NAPCAT_PORT", "8082"))
    except ValueError:
        raise ValueError("NAPCAT_PORT 须为整数。") from None
    if not 1024 <= port <= 65535:
        raise ValueError("NAPCAT_PORT 须为 1024—65535。")
    return token, port


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    base_url: str = field(repr=False)
    model: str = field(repr=False)
    api_key: str = field(repr=False)
    max_tokens: int = 2048
    extra_body: dict[str, Any] = field(default_factory=dict, repr=False)
    token_param: str = "max_tokens"

    @property
    def endpoint(self) -> str:
        if self.provider == "gemini":
            model = self.model.removeprefix("models/")
            return self.base_url + "/models/" + quote(model, safe="") + ":generateContent"
        if self.provider == "anthropic":
            if self.base_url.endswith("/messages"):
                return self.base_url
            return self.base_url + ("/messages" if self.base_url.endswith("/v1") else "/v1/messages")
        suffix = "/responses" if self.provider == "openai" else "/chat/completions"
        if self.base_url.endswith(suffix):
            return self.base_url
        return self.base_url + suffix


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str = field(default="", repr=False)
    deepseek_model: str = field(default="deepseek-flash", repr=False)
    bot_name: str = field(default=DEFAULT_BOT_NAME, repr=False)
    allowed_groups: frozenset[str] = field(default_factory=frozenset, repr=False)
    history_turns: int = 6
    cooldown_seconds: float = 3.0
    llm_provider: str = "deepseek"
    llm_base_url: str = field(default="", repr=False)
    llm_model: str = field(default="", repr=False)
    llm_api_key: str = field(default="", repr=False)
    llm_max_tokens: int = 2048
    llm_extra_body: dict[str, Any] = field(default_factory=dict, repr=False)
    llm_token_param: str = "max_tokens"
    onebot_access_token: str = field(default="", repr=False)
    napcat_port: int = 8082
    napcat_self_id: str = field(default="", repr=False)
    vision_provider: str = field(default="compatible", repr=False)
    vision_base_url: str = field(default="", repr=False)
    vision_model: str = field(default="", repr=False)
    vision_api_key: str = field(default="", repr=False)
    serpapi_api_key: str = field(default="", repr=False)
    pexels_api_key: str = field(default="", repr=False)
    tavily_api_key: str = field(default="", repr=False)
    saucenao_api_key: str = field(default="", repr=False)

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(ROOT / ".env", override=False, encoding="utf-8")
        token, port = napcat_connection(os.environ)
        try:
            turns = int(os.getenv("HISTORY_TURNS", "6"))
            cooldown = float(os.getenv("COOLDOWN_SECONDS", "3"))
            max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2048"))
        except ValueError:
            raise ValueError("轮数、输出预算和端口须为整数，冷却时间须为数字。") from None
        if not 0 <= turns <= 10 or not 0 <= cooldown <= 60:
            raise ValueError("HISTORY_TURNS 须为 0—10，COOLDOWN_SECONDS 须为 0—60。")
        try:
            extra_body = json.loads(os.getenv("LLM_EXTRA_BODY", "").strip() or "{}")
        except ValueError:
            raise ValueError("LLM_EXTRA_BODY 须为 JSON 对象。") from None
        settings = cls(
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip(),
            bot_name=os.getenv("BOT_NAME", "").strip() or DEFAULT_BOT_NAME,
            allowed_groups=frozenset(
                item.strip() for item in os.getenv("NAPCAT_ALLOWED_GROUPS", "").split(",") if item.strip()
            ),
            history_turns=turns,
            cooldown_seconds=cooldown,
            llm_provider=os.getenv("LLM_PROVIDER", "deepseek").strip().lower() or "deepseek",
            llm_base_url=os.getenv("LLM_BASE_URL", "").strip(),
            llm_model=os.getenv("LLM_MODEL", "").strip(),
            llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
            llm_max_tokens=max_tokens,
            llm_extra_body=extra_body,
            llm_token_param=os.getenv("LLM_TOKEN_PARAM", "max_tokens").strip() or "max_tokens",
            onebot_access_token=token,
            napcat_port=port,
            napcat_self_id=os.getenv("NAPCAT_SELF_ID", "").strip(),
            vision_provider=os.getenv("VISION_PROVIDER", "compatible").strip() or "compatible",
            vision_base_url=os.getenv("VISION_BASE_URL", "").strip(),
            vision_model=os.getenv("VISION_MODEL", "").strip(),
            vision_api_key=os.getenv("VISION_API_KEY", "").strip(),
            serpapi_api_key=os.getenv("SERPAPI_API_KEY", "").strip(),
            pexels_api_key=os.getenv("PEXELS_API_KEY", "").strip(),
            tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
            saucenao_api_key=os.getenv("SAUCENAO_API_KEY", "").strip(),
        )
        settings.resolve_llm()
        settings.resolve_vision()
        return settings

    def resolve_vision(self) -> ModelConfig | None:
        if not (self.vision_base_url or self.vision_model or self.vision_api_key):
            return None
        if self.vision_provider not in ("compatible", "openai", "anthropic", "gemini", "ollama"):
            raise ValueError("请选择支持图片输入的视觉接口类型。")
        return Settings(
            llm_provider=self.vision_provider, llm_base_url=self.vision_base_url,
            llm_model=self.vision_model, llm_api_key=self.vision_api_key,
            llm_max_tokens=self.llm_max_tokens,
        ).resolve_llm()

    def validate_napcat(self) -> None:
        if len(self.onebot_access_token) < 16:
            raise ValueError("请在本机配置至少 16 位的 ONEBOT_ACCESS_TOKEN，并在 NapCat 填相同 Token。")
        if not self.allowed_groups or any(not value.isascii() or not value.isdigit() for value in self.allowed_groups):
            raise ValueError("NAPCAT_ALLOWED_GROUPS 须填写允许使用的真实 QQ 群号。")
        if self.napcat_self_id and (not self.napcat_self_id.isascii() or not self.napcat_self_id.isdigit()):
            raise ValueError("NAPCAT_SELF_ID 须为数字 QQ 号。")

    def resolve_llm(self) -> ModelConfig:
        provider = self.llm_provider.strip().lower()
        if provider not in LLM_DEFAULTS:
            raise ValueError("LLM_PROVIDER 须为 deepseek、compatible、ollama、openai、anthropic 或 gemini。")
        if not 16 <= self.llm_max_tokens <= 32768:
            raise ValueError("LLM_MAX_TOKENS 须为 16—32768。")
        if self.llm_token_param not in ("max_tokens", "max_completion_tokens"):
            raise ValueError("LLM_TOKEN_PARAM 须为 max_tokens 或 max_completion_tokens。")
        if not isinstance(self.llm_extra_body, dict) or RESERVED_MODEL_FIELDS.intersection(self.llm_extra_body):
            raise ValueError("LLM_EXTRA_BODY 须为对象，且不能覆盖模型、消息、流式开关和输出上限等核心字段。")
        if "generationConfig" in self.llm_extra_body and not isinstance(self.llm_extra_body["generationConfig"], dict):
            raise ValueError("LLM_EXTRA_BODY 中的 generationConfig 须为对象。")
        default_url, default_model = LLM_DEFAULTS[provider]
        base_url = (self.llm_base_url.strip() or default_url).rstrip("/")
        model = self.llm_model.strip()
        key = self.llm_api_key.strip()
        if provider == "deepseek":
            # 仅 DeepSeek 模式兼容旧变量，避免切换平台时发送旧平台的密钥。
            model = model or self.deepseek_model.strip() or default_model
            if base_url in DEEPSEEK_URLS:
                key = key or self.deepseek_api_key.strip()
        if not model:
            raise ValueError("请填写 LLM_MODEL，使用服务商提供或本机已安装的模型名称。")
        try:
            parsed = urlsplit(base_url)
            valid_url = (
                parsed.scheme in ("http", "https") and parsed.hostname
                and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment
            )
            parsed.port  # 触发无效端口检查，不在错误提示里回显地址。
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ValueError("LLM_BASE_URL 须为有效的 HTTP(S) API 地址，不含账号、密码、查询参数或片段。")
        return ModelConfig(provider, base_url, model, key, self.llm_max_tokens, dict(self.llm_extra_body), self.llm_token_param)

    def status(self) -> dict[str, object]:
        # 自检仅报告是否填写，始终不输出凭证值。
        model = self.resolve_llm()
        return {
            "BOT_NAME": "已设置",
            "TRANSPORT": "NapCat / OneBot V11 反向 WebSocket",
            "ONEBOT_ACCESS_TOKEN": "已填写" if self.onebot_access_token else "待填写",
            "NAPCAT_ALLOWED_GROUPS": "已设置" if self.allowed_groups else "待填写（当前不回复任何群）",
            "NAPCAT_PORT": self.napcat_port,
            "VISION": "已配置" if self.resolve_vision() else "待配置",
            "IMAGE_SEARCH": "已配置" if self.serpapi_api_key else "待配置",
            "REVERSE_IMAGE_SEARCH": "已配置" if self.saucenao_api_key or self.serpapi_api_key else "待配置",
            "KEYWORD_IMAGE_SEARCH": "已配置" if self.pexels_api_key else "待配置",
            "WEB_SEARCH": "已配置" if self.tavily_api_key else "待配置",
            "LLM_PROVIDER": model.provider,
            "LLM_BASE_URL": "已设置（地址已隐藏）",
            "LLM_MODEL": "已设置（名称已隐藏）",
            "LLM_MAX_TOKENS": model.max_tokens,
            "LLM_API_KEY": "已填写" if model.api_key else ("本机 Ollama 可留空" if model.provider == "ollama" else "待填写"),
            "HISTORY_TURNS": self.history_turns,
        }
