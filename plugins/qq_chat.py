from nonebot import logger, on_type
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment

from app.chat import ChatService
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
                await bot.send(event, MessageSegment.text("请在同一条消息中 @我，并附带一张图片；可用 /识图 或 /搜图。"))
                return
            if images is None:
                await bot.send(event, MessageSegment.text("图片功能尚未初始化，请重启机器人。"))
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
            lambda answer: bot.send(event, MessageSegment.text(answer)),
            operation=operation,
        )
    except Exception as error:
        # 不输出异常原文：其中可能包含请求数据或平台响应。
        logger.warning("QQ群回复失败，错误类型：{}", type(error).__name__)
