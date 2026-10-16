from nonebot import logger, on_type
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, Message, MessageSegment
from nonebot.message import event_preprocessor

from app.chat import ChatService
from app.commands import REVERSE_COMMANDS, WEB_COMMANDS
from app.diagnostics import diagnostics
from app.images import ImageService
from app.pexels import PexelsService, PhotoResult
from app.websearch import WebSearchService


async def explicitly_mentioned(bot: Bot, event: GroupMessageEvent) -> bool:
    # 用原始消息中的 @ 段判断，避免昵称、引用或 @全体成员触发。
    return any(
        s.type == "at" and str(s.data.get("qq")) == str(bot.self_id) for s in event.original_message
    )


chat = on_type(GroupMessageEvent, rule=explicitly_mentioned, priority=10, block=True)
service: ChatService | None = None
images: ImageService | None = None
pexels: PexelsService | None = None
websearch: WebSearchService | None = None


def set_service(value: ChatService) -> None:
    global service
    service = value


def set_images(value: ImageService) -> None:
    global images
    images = value


def set_pexels(value: PexelsService | None) -> None:
    global pexels
    pexels = value


def set_websearch(value: WebSearchService | None) -> None:
    global websearch
    websearch = value


@event_preprocessor
async def track_group_event(bot: Bot, event: Event) -> None:
    if not isinstance(event, GroupMessageEvent):
        return
    diagnostics.increment("group_events")
    if not await explicitly_mentioned(bot, event):
        return
    diagnostics.increment("mentioned_events")
    if service is None:
        return
    if str(event.user_id) == str(bot.self_id):
        diagnostics.increment("ignored_self")
    elif str(event.group_id) not in service.settings.allowed_groups:
        diagnostics.increment("ignored_group")
    elif service.settings.napcat_self_id and str(bot.self_id) != service.settings.napcat_self_id:
        diagnostics.increment("ignored_account")


@chat.handle()
async def handle_group_message(bot: Bot, event: GroupMessageEvent) -> None:
    if service is None or str(event.user_id) == str(bot.self_id):
        return
    if not await explicitly_mentioned(bot, event):
        return
    group = str(event.group_id)
    if group not in service.settings.allowed_groups:
        return
    if service.settings.napcat_self_id and str(bot.self_id) != service.settings.napcat_self_id:
        return
    key = (str(bot.self_id), group, event.get_user_id())
    diagnostics.increment("handled")
    send_failed = False
    photo_result: PhotoResult | None = None

    async def send_reply(answer: str) -> object:
        nonlocal send_failed
        try:
            reply = MessageSegment.text(answer)
            if photo_result is not None and photo_result.image:
                reply = Message(reply) + MessageSegment.image(photo_result.image)
            result = await bot.send(event, reply)
        except Exception:
            send_failed = True
            diagnostics.increment("reply_errors")
            raise
        diagnostics.increment("replies_sent")
        return result

    try:
        text = event.get_plaintext().strip()
        picture_segments = [s for s in event.original_message if s.type == "image"]
        parts = text.split(maxsplit=1)
        command = parts[0] if parts else ""
        question = parts[1] if len(parts) > 1 else ""
        operation = None
        if command in WEB_COMMANDS:
            if not question or picture_segments:
                await send_reply("联网搜索请发送：@我 /搜索 你想查的问题，无需附图。")
                return
            if websearch is None:
                await send_reply("联网搜索尚未初始化，请重启机器人。")
                return

            async def operation() -> str:
                return await websearch.search(question)

        # 关键词找图和图片溯源分别路由，避免把群图片交给摄影图库。
        elif command == "/找图" or (command == "/搜图" and not picture_segments):
            if picture_segments or not question:
                await send_reply(
                    "关键词找图请发送：@我 /找图 猫。不用附图；查图片出处可用 /搜图 加一张图片。"
                )
                return
            if pexels is None:
                await send_reply("关键词找图尚未初始化，请重启机器人。")
                return

            async def operation() -> str:
                nonlocal photo_result
                photo_result = await pexels.search(question)
                return photo_result.caption

        elif picture_segments or command == "/识图" or command in REVERSE_COMMANDS:
            if len(picture_segments) != 1:
                await send_reply("请在同一条消息中 @我，并附带一张图片；可用 /识图 或 /查出处。")
                return
            if images is None:
                await send_reply("图片功能尚未初始化，请重启机器人。")
                return
            segment = picture_segments[0]
            mode = "search" if command in REVERSE_COMMANDS else "analyze"
            prompt = question if command == "/识图" else text

            async def operation() -> str:
                return await images.process(segment.data.get("url", ""), mode, prompt)

        await service.handle(
            key,
            str(event.message_id),
            # 仅附图的消息默认识图；纯 @ 保留为空，由会话服务显示菜单。
            text or ("/识图" if picture_segments else ""),
            send_reply,
            operation=operation,
        )
    except Exception as error:
        if not send_failed:
            diagnostics.increment("reply_errors")
        # 不输出异常原文：其中可能包含请求数据或平台响应。
        logger.warning("QQ群回复失败，错误类型：{}", type(error).__name__)
