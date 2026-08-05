"""事件模型与类型枚举"""

import time
from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    """OneBot 事件类型（消息 / 请求 / 通知）"""
    MESSAGE = "message"                 # 群/私聊消息
    GROUP_REQUEST = "group_request"     # 入群申请 / 邀请（post_type=request, request_type=group）
    FRIEND_REQUEST = "friend_request"   # 加好友申请
    GROUP_INCREASE = "group_increase"   # 入群完成（notice_type=group_increase）
    GROUP_DECREASE = "group_decrease"   # 退群 / 被踢（notice_type=group_decrease）
    OTHER = "other"                     # 其他通知/未分类


@dataclass
class Event:
    """统一事件对象"""
    type: EventType
    data: dict                          # 原始 OneBot 事件 dict
    time: float = field(default_factory=time.time)

    @property
    def group_id(self):
        return self.data.get("group_id")

    @property
    def user_id(self) -> str:
        return str(self.data.get("user_id") or "")

    @property
    def raw_message(self):
        return self.data.get("raw_message")

    def __str__(self):
        return f"Event({self.type.value}, {self.data})"


def classify_event(data: dict) -> EventType:
    """根据原始 OneBot 消息分类事件类型"""
    post_type = data.get("post_type")
    if post_type == "message":
        return EventType.MESSAGE
    if post_type == "request":
        if data.get("request_type") == "group":
            return EventType.GROUP_REQUEST
        if data.get("request_type") == "friend":
            return EventType.FRIEND_REQUEST
        return EventType.OTHER
    if post_type == "notice":
        notice_type = data.get("notice_type")
        if notice_type == "group_increase":
            return EventType.GROUP_INCREASE
        if notice_type == "group_decrease":
            return EventType.GROUP_DECREASE
        return EventType.OTHER
    return EventType.OTHER
