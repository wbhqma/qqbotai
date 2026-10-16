"""群命令别名与功能菜单；菜单只读取配置，不调用外部服务。"""

from app.config import ModelConfig, Settings

HELP_COMMANDS = ("/帮助", "/help", "帮助")
PING_COMMANDS = ("/ping", "ping")
RESET_COMMANDS = ("/清空", "/reset", "清空记忆")
WEB_COMMANDS = ("/搜索", "/联网", "/search")
REVERSE_COMMANDS = ("/搜图", "/查出处", "/出处")


def _model_configured(config: ModelConfig | None) -> bool:
    return config is not None and bool(config.api_key or config.provider == "ollama")


def _status(configured: bool) -> str:
    return "已配置" if configured else "未配置"


def build_help(settings: Settings) -> str:
    """列出全部功能及本机配置状态，不回显凭证、地址或账号标识。"""
    text_ready = _model_configured(settings.resolve_llm())
    vision_ready = _model_configured(settings.resolve_vision())
    source_ready = bool(settings.saucenao_api_key or settings.serpapi_api_key)
    return "\n".join(
        (
            "我能做这些：",
            "所有用法都要先 @我；单独 @我 或发送 /帮助，可再次查看菜单。",
            "",
            f"聊天［{_status(text_ready)}］：@我 加上问题，支持近期文字记忆。",
            "/清空：忘记你在当前群的近期对话。",
            "/ping：检查是否在线，不调用模型。",
            "",
            f"/搜索 问题［{_status(bool(settings.tavily_api_key))}］：联网检索，附摘要与来源链接。",
            f"/识图 [问题] + 一张图［{_status(vision_ready)}］：看图回答、读图中文字；@我 加图也可。",
            f"/查出处 + 一张图［{_status(source_ready)}］：查插画候选作品页和相似度，或相似网页。",
            f"/找图 关键词［{_status(bool(settings.pexels_api_key))}］：找一张摄影图片，附署名与来源。",
            "",
            "别名：/联网、/search = /搜索；/出处 = /查出处；/reset = /清空；/help = /帮助。",
            "/搜图 加一张图 = /查出处；/搜图 加关键词（不附图）= /找图。",
            "",
            "图片与命令放在同一条消息，一次一张。未配置的功能需管理员先配置。",
            "识图和查出处会把本次图片发给对应服务；联网搜索会把问题交给搜索服务和模型。",
            "文字记忆按群和用户隔离，重启清空。已配置仅表示填好了配置。",
        )
    )
