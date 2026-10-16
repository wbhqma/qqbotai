"""只累计固定事件计数，不保存消息、账号、时间或异常内容。"""


COUNTERS = (
    "group_events",
    "mentioned_events",
    "ignored_self",
    "ignored_group",
    "ignored_account",
    "handled",
    "replies_sent",
    "reply_errors",
)


class Diagnostics:
    def __init__(self) -> None:
        self._counts = dict.fromkeys(COUNTERS, 0)

    def increment(self, name: str) -> None:
        if name not in self._counts:
            raise ValueError("不支持的诊断计数项。")
        self._counts[name] += 1

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)

    def reset(self) -> None:
        self._counts = dict.fromkeys(COUNTERS, 0)


diagnostics = Diagnostics()
