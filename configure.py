import argparse
import json
import secrets
import tempfile
from getpass import getpass
from pathlib import Path

from dotenv import dotenv_values, set_key

from app.config import DEFAULT_BOT_NAME, DEEPSEEK_URLS, LLM_DEFAULTS, ROOT, Settings


def check_configuration() -> int:
    """只读检查启动所需配置，不显示配置值或进入交互向导。"""
    try:
        settings = Settings.load()
        settings.validate_napcat()
    except (ValueError, OSError, UnicodeError):
        print("配置未就绪：请运行本机配置向导，检查连接凭证、允许的群及字段格式；配置值已隐藏。")
        return 2
    print("启动配置检查通过；配置值已隐藏，未连接 QQ 或外部服务。")
    return 0


def configure_groups() -> int:
    """只修改群白名单，其他本机配置不重新收集或重建。"""
    path = ROOT / ".env"
    values = dotenv_values(path, encoding="utf-8", interpolate=False) if path.exists() else {}
    print("仅修改允许的群。直接回车保留已有设置；尚未设置时须填写。群号不会回显。")
    entered = getpass("允许的真实QQ群号（输入不显示字符，多个用英文逗号分隔）：").strip()
    raw = entered or values.get("NAPCAT_ALLOWED_GROUPS") or ""
    groups = [item.strip() for item in raw.split(",") if item.strip()]
    try:
        Settings(onebot_access_token="0123456789abcdef", allowed_groups=frozenset(groups)).validate_napcat()
    except ValueError:
        print("群设置无效：须填写至少一个由 ASCII 数字组成的真实群号；本次未修改配置，具体值已隐藏。")
        return 2
    if not entered:
        print("已保留原有群设置；其他配置未修改，具体值已隐藏。")
        return 0
    original = path.read_bytes() if path.exists() else b""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=ROOT, prefix=".env.groups-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(original)
        set_key(temporary, "NAPCAT_ALLOWED_GROUPS", ",".join(dict.fromkeys(groups)), encoding="utf-8")
        # set_key 会规范换行；保留原文件常用的 LF / CRLF 格式。
        newline = "\r\n" if b"\r\n" in original else "\n"
        updated = temporary.read_text(encoding="utf-8")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            stream.write(updated.replace("\n", newline))
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print("允许的群已保存；请重启 AI 程序使设置生效。其他配置保留，具体值已隐藏。")
    return 0


def configure() -> int:
    path = ROOT / ".env"
    values = dict(dotenv_values(path, encoding="utf-8")) if path.exists() else {}
    print("在本机配置 NapCat。QQ 号、群号和密钥输入不回显；已有值可留空保留。")
    for name, title, secret in (
        ("ONEBOT_ACCESS_TOKEN", "OneBot Token（留空保留或自动生成；NapCat 需填写相同值）", True),
        ("NAPCAT_ALLOWED_GROUPS", "允许的真实 QQ 群号（多个用英文逗号分隔，必填）", True),
        ("NAPCAT_SELF_ID", "机器人个人 QQ 号（可选）", True),
    ):
        hint = " [已保存，留空保留]" if values.get(name) else ""
        prompt = title + hint + "："
        value = (getpass(prompt) if secret else input(prompt)).strip()
        if value:
            values[name] = value
    values.setdefault("ONEBOT_ACCESS_TOKEN", "")
    if not values["ONEBOT_ACCESS_TOKEN"]:
        values["ONEBOT_ACCESS_TOKEN"] = secrets.token_urlsafe(32)
    values.setdefault("NAPCAT_PORT", "8082")
    current_name = values.get("BOT_NAME") or DEFAULT_BOT_NAME
    values["BOT_NAME"] = input("机器人名字（留空保留；已有名字不回显）：").strip() or current_name
    old_provider = (values.get("LLM_PROVIDER") or "deepseek").strip().lower()
    print("接入方式：deepseek；compatible（千问等兼容接口）；openai（GPT）；anthropic（Claude）；gemini；ollama（本机）。")
    provider_hint = old_provider if old_provider in LLM_DEFAULTS else "需重新选择"
    provider = input(f"模型接入方式 [{provider_hint}]：").strip().lower() or old_provider
    if provider not in LLM_DEFAULTS:
        print("接入方式无效，请选择上方列出的名称；本次未写入配置。")
        return 2
    default_url, default_model = LLM_DEFAULTS[provider]
    same_provider = provider == old_provider
    current_url = (values.get("LLM_BASE_URL") if same_provider else "") or default_url
    current_model = (values.get("LLM_MODEL") if same_provider else "") or default_model
    current_key = (values.get("LLM_API_KEY") if same_provider else "") or ""
    if provider == "deepseek" and same_provider:
        current_model = values.get("LLM_MODEL") or values.get("DEEPSEEK_MODEL") or default_model
        if current_url.rstrip("/") in DEEPSEEK_URLS:
            current_key = current_key or values.get("DEEPSEEK_API_KEY") or ""
    base_url = input("API 地址（留空保留或使用该接入方式的默认地址；已有地址不回显）：").strip() or current_url
    model_name = input("模型名称（留空保留或使用该接入方式的默认模型；已有名称不回显）：").strip() or current_model
    endpoint_changed = base_url.rstrip("/") != current_url.rstrip("/")
    if endpoint_changed:
        current_key = ""
        print("API 地址已改变，请填写对应服务的密钥；不沿用旧地址的密钥。")
    key_hint = "已保存，留空保留" if current_key else "可稍后填写；本机 Ollama 可留空"
    api_key = getpass(f"当前模型服务 API Key（{key_hint}）：").strip() or current_key
    values.update(LLM_PROVIDER=provider, LLM_BASE_URL=base_url, LLM_MODEL=model_name, LLM_API_KEY=api_key)
    # 将旧 DeepSeek 配置迁移为当前服务的通用配置，清空密钥时不会又回退到旧变量。
    values.pop("DEEPSEEK_API_KEY", None)
    values.pop("DEEPSEEK_MODEL", None)
    if not same_provider or endpoint_changed:
        # 专用请求参数不能自动带到另一个协议/平台。
        values.pop("LLM_EXTRA_BODY", None)
        values.pop("LLM_TOKEN_PARAM", None)
    try:
        Settings(llm_provider=provider, llm_base_url=base_url, llm_model=model_name, llm_api_key=api_key).resolve_llm()
    except ValueError:
        print("模型配置需要调整：请检查 API 地址、模型名称和接入方式；本次未写入配置。")
        return 2
    try:
        candidate = Settings(
            onebot_access_token=values["ONEBOT_ACCESS_TOKEN"],
            allowed_groups=frozenset(v.strip() for v in (values.get("NAPCAT_ALLOWED_GROUPS") or "").split(",") if v.strip()),
            napcat_self_id=values.get("NAPCAT_SELF_ID") or "",
        )
        candidate.validate_napcat()
        if not 1024 <= int(values["NAPCAT_PORT"]) <= 65535:
            raise ValueError
    except ValueError:
        print("NapCat 配置需要调整：Token 至少 16 位，允许的群须为数字群号，端口须为 1024—65535；本次未写入配置。")
        return 2
    print("可选图片功能：视觉模型与搜图使用独立凭证。只在群内明确请求时上传图片。")
    if input("现在配置或修改视觉模型？[y/N]：").strip().lower() == "y":
        old_vision_provider = values.get("VISION_PROVIDER") or "compatible"
        vision_provider = input("视觉接口类型 compatible/openai/anthropic/gemini/ollama（留空保留）：").strip() or old_vision_provider
        same_vision_provider = vision_provider == old_vision_provider
        vision_url = input("视觉 API 地址（留空保留或使用该协议默认地址）：").strip() or (
            (values.get("VISION_BASE_URL") if same_vision_provider else "") or LLM_DEFAULTS.get(vision_provider, ("", ""))[0]
        )
        same_vision_endpoint = same_vision_provider and vision_url.rstrip("/") == (values.get("VISION_BASE_URL") or LLM_DEFAULTS.get(old_vision_provider, ("", ""))[0]).rstrip("/")
        vision_model = input("支持图片输入的视觉模型名称（留空保留）：").strip() or ((values.get("VISION_MODEL") if same_vision_endpoint else "") or "")
        vision_key = getpass("视觉 API Key（留空保留同一接口已有值；输入 - 清空）：").strip()
        if vision_key == "-":
            vision_key = ""
        elif not vision_key and same_vision_endpoint:
            vision_key = values.get("VISION_API_KEY") or ""
        try:
            Settings(vision_provider=vision_provider, vision_base_url=vision_url,
                     vision_model=vision_model, vision_api_key=vision_key).resolve_vision()
        except ValueError:
            print("视觉模型配置无效；本次未写入配置。")
            return 2
        values.update(VISION_PROVIDER=vision_provider, VISION_BASE_URL=vision_url,
                      VISION_MODEL=vision_model, VISION_API_KEY=vision_key)
    if input("现在配置或修改搜图服务 SerpApi？[y/N]：").strip().lower() == "y":
        search_key = getpass("SerpApi API Key（留空保留；输入 - 清空）：").strip()
        values["SERPAPI_API_KEY"] = "" if search_key == "-" else (search_key or values.get("SERPAPI_API_KEY") or "")
    for name, default in (
        ("LLM_MAX_TOKENS", "2048"), ("LLM_EXTRA_BODY", "{}"),
        ("LLM_TOKEN_PARAM", "max_tokens"),
        ("HISTORY_TURNS", "6"), ("COOLDOWN_SECONDS", "3"),
        ("VISION_PROVIDER", "compatible"), ("VISION_BASE_URL", ""), ("VISION_MODEL", ""),
        ("VISION_API_KEY", ""), ("SERPAPI_API_KEY", ""),
    ):
        values.setdefault(name, default)
    for retired in ("QQ_APP_ID", "QQ_APP_SECRET", "QQ_ALLOWED_GROUPS"):
        values.pop(retired, None)
    text = "# 本机凭证配置，请勿提交到 Git 或上传到学习文档。\n"
    text += "\n".join(f"{name}={json.dumps(value or '', ensure_ascii=False)}" for name, value in values.items())
    path.write_text(text + "\n", encoding="utf-8")
    print("配置已保存到本项目 .env；运行或重启 start-napcat.ps1 会自动同步连接配置，密钥未输出。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="配置 qqbotai 的本机连接与模型服务")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只读检查配置，不交互或连接外部服务")
    mode.add_argument("--groups", action="store_true", help="仅修改允许的真实群号，不重填模型配置")
    args = parser.parse_args(argv)
    if args.groups:
        return configure_groups()
    return check_configuration() if args.check else configure()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("\n已取消配置。")
        raise SystemExit(1)
    except Exception:
        print("配置失败：请检查本机文件权限和依赖安装；错误详情已隐藏。")
        raise SystemExit(1)
