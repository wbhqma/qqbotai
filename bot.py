import argparse
import json

import httpx

import nonebot
from nonebot.adapters.onebot.v11 import Adapter

from app.chat import ChatService
from app.config import Settings
from app.diagnostics import diagnostics
from app.llm import LLMClient
from app.images import ImageService
from app.privacy import configure_private_logging


def build_bot(settings: Settings, *, offline: bool = False) -> None:
    configure_private_logging()
    nonebot.init(
        driver="~fastapi+~httpx+~websockets",
        host="127.0.0.1",
        port=settings.napcat_port,
        log_level="INFO",
        nickname=set(),
        onebot_access_token=settings.onebot_access_token or ("offline-check-only" if offline else ""),
        onebot_ws_urls=[],
        onebot_api_roots={},
    )
    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)

    @driver.server_app.get("/qqbotai/health", include_in_schema=False)
    async def health() -> dict[str, object]:
        connected = any(not settings.napcat_self_id or bot.self_id == settings.napcat_self_id
                        for bot in nonebot.get_bots().values())
        return {"service": "qqbotai", "connected": connected,
                "groups_configured": bool(settings.allowed_groups),
                "diagnostics": diagnostics.snapshot()}
    plugin = nonebot.load_plugin("plugins.qq_chat")
    if plugin is None:
        raise RuntimeError("聊天插件加载失败。")
    model = LLMClient(settings)
    plugin.module.set_service(ChatService(settings, model))
    images = ImageService(settings)
    plugin.module.set_images(images)
    driver.on_shutdown(model.close)
    driver.on_shutdown(images.close)


def main() -> int:
    configure_private_logging()
    parser = argparse.ArgumentParser(description="qqbotai：使用你自己的 QQ 账号运行群聊 AI")
    parser.add_argument("--check", action="store_true", help="检查配置与插件，不连接 QQ 或模型")
    parser.add_argument("--status", action="store_true", help="只查询本机 qqbotai 是否运行及连接，不显示账号信息")
    parser.add_argument("--diagnose", action="store_true", help="查询本机匿名事件计数，不显示消息、账号或群号")
    args = parser.parse_args()
    try:
        settings = Settings.load()
        if args.status or args.diagnose:
            try:
                response = httpx.get(f"http://127.0.0.1:{settings.napcat_port}/qqbotai/health", timeout=3, trust_env=False)
                response.raise_for_status()
                status = response.json()
                if status.get("service") != "qqbotai":
                    raise ValueError
                print("qqbotai 已运行；" + ("QQ 连接已建立。" if status.get("connected") else "等待 NapCat 登录或连接。"))
                if args.diagnose:
                    counts = status.get("diagnostics", {})
                    if not isinstance(counts, dict):
                        raise ValueError
                    safe_counts = {key: max(0, value) if type(value) is int else 0
                                   for key in diagnostics.snapshot()
                                   for value in (counts.get(key, 0),)}
                    print(json.dumps(safe_counts, ensure_ascii=False, indent=2))
                return 0 if status.get("connected") else 2
            except (httpx.HTTPError, ValueError, AttributeError):
                print("qqbotai 尚未运行或本机状态不可读取。")
                return 2
        if args.check:
            print(json.dumps(settings.status(), ensure_ascii=False, indent=2))
            build_bot(settings, offline=True)
            print("离线自检通过：OneBot 适配器、聊天和图片插件已加载；未连接 QQ、模型或搜索服务。")
            return 0
        settings.validate_napcat()
        build_bot(settings)
        print(f"等待 NapCat 连接：ws://127.0.0.1:{settings.napcat_port}/onebot/v11/，连接后在允许的群 @我 /ping。")
        nonebot.run()
    except ValueError:
        print("配置需要调整：请运行 configure.py，检查 Token、允许的群号及模型/视觉接口；配置值已隐藏。")
        return 2
    except KeyboardInterrupt:
        print("机器人已停止。")
        return 0
    except Exception:
        nonebot.logger.exception("机器人启动或运行失败。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
