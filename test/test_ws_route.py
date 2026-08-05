"""
ws_connect 消息路由测试：API 响应（echo）分流与事件总线分发

运行: uv run python test/test_ws_route.py
"""
import asyncio
import json
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.ws_connect as ws_mod
from api.Botapi import QQAPI_list
from api.ws_connect import Websocket_receiver
from app.core.events import event_bus, EventType

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


class FakeConn:
    """mock websocket 连接：send 记录，迭代产出消息序列"""
    def __init__(self, msgs):
        self.msgs = list(msgs)
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))

    def __aiter__(self):
        self._it = iter(self.msgs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeConnect:
    """mock websockets.connect 上下文管理器"""
    def __init__(self, msgs):
        self.conn = FakeConn(msgs)

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


def test_route_echo_and_event():
    print("\n[1] 完整接收循环：API 响应分流 + 事件总线分发")
    msg_hello = json.dumps({"post_type": "message", "message_type": "group",
                            "raw_message": "hello", "group_id": "g1", "user_id": "u1"})

    async def scenario():
        # 构造：先发起一个 API 调用（发送后取得 echo），再构造接收消息序列
        results = {}
        events = []

        async def on_message(event):
            events.append(event)

        # 手动构造 receiver，模拟连接流程
        conn = FakeConn([])
        api = QQAPI_list(conn)
        recv = Websocket_receiver()
        recv.api = api

        # 发起 _call（等价 _route_message 收到响应前的 pending 注册）
        call_task = asyncio.create_task(api._call("get_group_info", {"group_id": "1"}, timeout=5))
        await asyncio.sleep(0.05)
        echo = conn.sent[-1]["echo"]

        # 接收序列：先事件消息，再 API 响应
        resp = json.dumps({"status": "ok", "retcode": 0, "data": {"group_id": "1"},
                           "message": "", "echo": echo})
        conn.msgs = [msg_hello, resp]

        # 订阅 MESSAGE 事件，模拟 ws 层闭包订阅
        event_bus.subscribe(EventType.MESSAGE, on_message)

        # 模拟接收循环（修复后：事件处理后台化，不阻塞 recv）
        tasks = []
        async for raw in conn:
            data = json.loads(raw)
            if not recv._route_message(data):
                tasks.append(asyncio.create_task(event_bus.emit_raw(data)))
        await asyncio.gather(*tasks)

        ok, data, msg = await call_task
        event_bus.unsubscribe(EventType.MESSAGE, on_message)
        return ok, data, events

    ok, data, events = asyncio.run(scenario())
    check("API 响应经 echo 匹配回流", ok and data["group_id"] == "1", (ok, data))
    check("事件消息走事件总线", len(events) == 1 and events[0].raw_message == "hello", str(events))
    check("响应消息未产生事件", all(e.type != EventType.OTHER for e in events), str(events))


def test_route_unknown_echo_ignored():
    print("\n[2] 未匹配 echo 按事件处理（不会崩溃）")
    recv = Websocket_receiver()
    recv.api = QQAPI_list(FakeConn([]))

    unknown = json.dumps({"status": "ok", "echo": "ghost-echo"})
    data = json.loads(unknown)
    routed = recv._route_message(data)
    check("未匹配 echo 不路由为响应", routed is False)


def test_event_classification_through_ws():
    print("\n[3] request/notice 事件经 ws 层进入事件总线（分类正确）")
    received = []

    async def on_req(event):
        received.append(event)

    event_bus.subscribe(EventType.GROUP_REQUEST, on_req)

    async def scenario():
        req = json.dumps({"post_type": "request", "request_type": "group",
                          "sub_type": "add", "group_id": "g9", "user_id": "u9", "flag": "f1"})
        recv = Websocket_receiver()
        recv.api = QQAPI_list(FakeConn([]))
        data = json.loads(req)
        if not recv._route_message(data):
            await event_bus.emit_raw(data)

    asyncio.run(scenario())
    event_bus.unsubscribe(EventType.GROUP_REQUEST, on_req)
    check("入群请求事件分类正确", len(received) == 1 and received[0].type == EventType.GROUP_REQUEST
          and received[0].data["flag"] == "f1", str(received))


def test_msg_dispatcher_driven_by_event():
    print("\n[4] MESSAGE 事件驱动 dispatcher（闭包订阅链）")
    # 模拟 ws_connect 中"连接建立 → 订阅 MESSAGE → 事件分发"全链
    dispatched = []

    async def fake_dispatch(ws, data):
        dispatched.append(data.get("raw_message"))

    class FakeDispatcher:
        async def handle_event(self, ws, data):
            await fake_dispatch(ws, data)

    async def scenario():
        conn = FakeConn([json.dumps({"post_type": "message", "message_type": "group",
                                     "raw_message": "hi", "group_id": "g", "user_id": "u"})])
        dispatcher = FakeDispatcher()
        handler = None

        async def _on_message(event):
            await dispatcher.handle_event(conn, event.data)

        handler = _on_message
        event_bus.subscribe(EventType.MESSAGE, handler)
        try:
            async for raw in conn:
                data = json.loads(raw)
                if not False:
                    await event_bus.emit_raw(data)
        finally:
            event_bus.unsubscribe(EventType.MESSAGE, handler)

    asyncio.run(scenario())
    check("MESSAGE 事件驱动 dispatcher", dispatched == ["hi"], str(dispatched))


def test_event_api_response_no_deadlock():
    print("\n[5] 自锁回归：事件处理中调 API，响应能在处理期间被读取循环投递")
    # 修复前：ws 循环串行 await emit_raw → dispatch 等 API 响应 → 响应读不到 → 10s 超时
    # 修复后：事件处理后台化，读取循环立即回到 recv，响应及时投递

    async def scenario():
        conn = FakeConn([])
        api = QQAPI_list(conn)
        recv = Websocket_receiver()
        recv.api = api
        result = {}

        async def on_message(event):
            ok, data, msg = await api._call("get_group_member_info", {"group_id": "1", "user_id": "2"}, timeout=3)
            result["r"] = (ok, data)

        event_bus.subscribe(EventType.MESSAGE, on_message)
        try:
            # 第一步：收到群消息 → 后台处理（emit_raw）
            msg1 = json.dumps({"post_type": "message", "message_type": "group",
                               "raw_message": "/active", "group_id": "g1", "user_id": "u1"})
            data1 = json.loads(msg1)
            assert not recv._route_message(data1)
            task = asyncio.create_task(event_bus.emit_raw(data1))

            # 等事件处理发出 API 请求，取 echo
            await asyncio.sleep(0.05)
            echo = conn.sent[-1]["echo"]

            # 第二步：模拟读取循环继续 recv → API 响应到达 → 路由投递
            resp = json.dumps({"status": "ok", "retcode": 0, "data": {"user_id": "2"},
                               "message": "", "echo": echo})
            data2 = json.loads(resp)
            routed = recv._route_message(data2)

            await task
            return routed, result.get("r")
        finally:
            event_bus.unsubscribe(EventType.MESSAGE, on_message)

    routed, r = asyncio.run(scenario())
    check("响应被读取循环投递", routed is True)
    check("事件处理拿到 API 响应（未超时）", r == (True, {"user_id": "2"}), str(r))


if __name__ == "__main__":
    test_route_echo_and_event()
    test_route_unknown_echo_ignored()
    test_event_classification_through_ws()
    test_msg_dispatcher_driven_by_event()
    test_event_api_response_no_deadlock()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
