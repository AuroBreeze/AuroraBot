"""
事件总线（app/core/events/bus.py）

统一事件分发：ws 连接层把每条 OneBot 消息喂给 EventBus，
各 app 通过 subscribe 订阅自己关心的事件类型（消息/入群请求/入群完成/退群...）。

- 订阅者异常隔离：单个订阅者抛异常不影响其他订阅者与后续分发
- 支持热更新：unsubscribe / unsubscribe_all 供业务层重载时清理旧订阅
"""
from typing import Awaitable, Callable

from api.Logger_owner import Logger
from .model import Event, EventType, classify_event

# 事件订阅者签名: async (event: Event) -> None
EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """事件分发单例"""

    def __init__(self):
        self.logger = Logger("event_bus")
        self._subscribers: dict[EventType, list[EventHandler]] = {}

    # ---------- 订阅 ----------

    def subscribe(self, event_type: EventType, handler: EventHandler) -> EventHandler:
        """订阅指定类型事件；重复订阅同一 handler 去重"""
        handlers = self._subscribers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)
        return handler

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> bool:
        """取消单个订阅"""
        handlers = self._subscribers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)
            return True
        return False

    def unsubscribe_all(self, event_type: EventType) -> int:
        """清空某类型全部订阅（热更新时使用），返回移除数量"""
        handlers = self._subscribers.pop(event_type, [])
        return len(handlers)

    def subscriber_count(self, event_type: EventType) -> int:
        return len(self._subscribers.get(event_type, []))

    # ---------- 分发 ----------

    async def emit(self, event: Event) -> None:
        """按事件类型分发；订阅者异常隔离"""
        handlers = list(self._subscribers.get(event.type, []))
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                self.logger.error(f"事件订阅者异常 ({event.type}): {e}")
                import traceback
                traceback.print_exc()

    async def emit_raw(self, data: dict) -> Event:
        """ws 接收层入口：原始 OneBot 消息 → 分类 → 分发，返回 Event"""
        event = Event(type=classify_event(data), data=data)
        await self.emit(event)
        return event


# 全局单例
event_bus = EventBus()
