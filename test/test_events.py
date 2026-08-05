"""
事件总线测试

运行: uv run python test/test_events.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.events import event_bus, Event, EventType, classify_event, EventBus

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


def test_classify():
    print("\n[1] 事件分类")
    check("群消息", classify_event({"post_type": "message", "message_type": "group"}) == EventType.MESSAGE)
    check("入群申请", classify_event({"post_type": "request", "request_type": "group", "sub_type": "add"}) == EventType.GROUP_REQUEST)
    check("加好友申请", classify_event({"post_type": "request", "request_type": "friend"}) == EventType.FRIEND_REQUEST)
    check("入群完成", classify_event({"post_type": "notice", "notice_type": "group_increase"}) == EventType.GROUP_INCREASE)
    check("退群", classify_event({"post_type": "notice", "notice_type": "group_decrease"}) == EventType.GROUP_DECREASE)
    check("其他通知", classify_event({"post_type": "notice", "notice_type": "poke"}) == EventType.OTHER)
    check("未知", classify_event({"foo": 1}) == EventType.OTHER)


def test_subscribe_emit():
    print("\n[2] 订阅与分发")
    bus = EventBus()
    received = []

    async def h1(event):
        received.append(("h1", event.type, event.user_id, event.group_id))

    async def h2(event):
        received.append(("h2", event.type))

    bus.subscribe(EventType.GROUP_INCREASE, h1)
    bus.subscribe(EventType.GROUP_INCREASE, h2)

    asyncio.run(bus.emit(Event(type=EventType.GROUP_INCREASE, data={"group_id": "g1", "user_id": "u9"})))
    check("订阅者收到事件", len(received) == 2, str(received))
    check("事件字段访问", received[0][2] == "u9" and received[0][3] == "g1", str(received))

    # 未订阅类型不触发
    received.clear()
    asyncio.run(bus.emit(Event(type=EventType.MESSAGE, data={})))
    check("未订阅类型不触发", received == [])


def test_exception_isolation():
    print("\n[3] 订阅者异常隔离")
    bus = EventBus()
    order = []

    async def boom(event):
        raise RuntimeError("boom")

    async def ok(event):
        order.append("ok")

    bus.subscribe(EventType.MESSAGE, boom)
    bus.subscribe(EventType.MESSAGE, ok)
    asyncio.run(bus.emit(Event(type=EventType.MESSAGE, data={})))
    check("异常订阅者不影响后续", order == ["ok"], str(order))


def test_emit_raw_and_unsubscribe():
    print("\n[4] emit_raw 分类分发 + 退订")
    bus = EventBus()
    seen = []

    async def h(event):
        seen.append(event.type)

    bus.subscribe(EventType.GROUP_REQUEST, h)
    asyncio.run(bus.emit_raw({"post_type": "request", "request_type": "group", "sub_type": "invite"}))
    check("emit_raw 自动分类分发", seen == [EventType.GROUP_REQUEST], str(seen))

    bus.unsubscribe(EventType.GROUP_REQUEST, h)
    seen.clear()
    asyncio.run(bus.emit_raw({"post_type": "request", "request_type": "group"}))
    check("unsubscribe 后不再分发", seen == [])

    bus.subscribe(EventType.MESSAGE, h)
    bus.subscribe(EventType.MESSAGE, h)  # 重复订阅去重
    bus.unsubscribe_all(EventType.MESSAGE)
    check("unsubscribe_all 清空", bus.subscriber_count(EventType.MESSAGE) == 0)


if __name__ == "__main__":
    test_classify()
    test_subscribe_emit()
    test_exception_isolation()
    test_emit_raw_and_unsubscribe()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
