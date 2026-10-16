from nonebot import logger, on_type
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, MessageSegment
from nonebot.message import event_preprocessor

from app.chat import ChatService
from app.diagnostics import diagnostics
from app.images import ImageService

async def explicitly_mentioned(bot: Bot, event: GroupMessageEvent) -> bool:
    # 用原始消息中的 @ 段判断，避免昵称、引用或 @全体成员触发。
    return any(s.type == "at" and str(s.data.get("qq")) == str(bot.self_id)
               for s in event.original_message)


chat = on_type(GroupMessageEvent, rule=explicitly_mentioned, priority=10, block=True)
service: ChatService | None = None
images: ImageService | None = None


def set_service(value: ChatService) -> None:
    global service
    service = value


def set_images(value: ImageService) -> None:
    global images
    images = value


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

    async def send_reply(answer: str) -> object:
        nonlocal send_failed
        try:
            result = await bot.send(event, MessageSegment.text(answer))
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
        # 图片消息默认识图；精确命令 /搜图 才会交给搜索服务。
        if picture_segments or command in ("/识图", "/搜图"):
            if len(picture_segments) != 1:
                await send_reply("请在同一条消息中 @我，并附带一张图片；可用 /识图 或 /搜图。")
                return
            if images is None:
                await send_reply("图片功能尚未初始化，请重启机器人。")
                return
            segment = picture_segments[0]
            mode = "search" if command == "/搜图" else "analyze"
            prompt = question if command == "/识图" else text
            async def operation() -> str:
                return await images.process(segment.data.get("url", ""), mode, prompt)
        await service.handle(
            key,
            str(event.message_id),
            text or "/识图",
            send_reply,
            operation=operation,
        )
    except Exception as error:
        if not send_failed:
            diagnostics.increment("reply_errors")
        # 不输出异常原文：其中可能包含请求数据或平台响应。
        logger.warning("QQ群回复失败，错误类型：{}", type(error).__name__)
