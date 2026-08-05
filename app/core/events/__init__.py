"""
事件系统（app/core/events/）

其他 app 接入方式：
    from app.core.events import event_bus, EventType

    async def on_group_increase(event):
        print("新成员:", event.user_id, "群:", event.group_id)

    event_bus.subscribe(EventType.GROUP_INCREASE, on_group_increase)

ws 连接层把每条 OneBot 消息通过 event_bus.emit_raw() 喂入，
事件按类型（MESSAGE / GROUP_REQUEST / GROUP_INCREASE / GROUP_DECREASE / ...）分发。
"""
from .model import Event, EventType, classify_event
from .bus import EventBus, EventHandler, event_bus

__all__ = ["Event", "EventType", "classify_event", "EventBus", "EventHandler", "event_bus"]
