"""
Botapi 客户端层测试：统一 _call 请求通道（echo 匹配）、API 封装

运行: uv run python test/test_botapi.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.Botapi import QQAPI_list

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


class MockWS:
    """mock websocket：记录发送，响应由测试手动注入（模拟 ws 接收层）"""
    def __init__(self):
        self.sent = []          # 发送的原始 json 字符串
        self.api = None         # 引用 QQAPI_list（模拟接收层回调）

    async def send(self, data):
        self.sent.append(json.loads(data))

    def deliver(self, data: dict):
        """模拟 ws 接收层：带 echo 的响应投递给 api.dispatch_response"""
        if self.api is not None and data.get("echo"):
            self.api.dispatch_response(data["echo"], data)

    def ok(self, data=None):
        return {"status": "ok", "retcode": 0, "data": data, "message": "", "echo": self.last_echo}

    def fail(self, message="boom"):
        return {"status": "failed", "retcode": 1400, "data": None, "message": message, "echo": self.last_echo}

    @property
    def last_echo(self):
        return self.sent[-1]["echo"] if self.sent else None


def make_api():
    ws = MockWS()
    api = QQAPI_list(ws)
    ws.api = api
    return ws, api


def test_cross_instance_response():
    print("\n[1b] 跨实例响应投递（进程级共享 pending 回归）")
    # 修复前：registry._reply 新建 QQAPI_list 实例 B，ws 层只查实例 A 的
    # _pending → 响应被当事件丢弃 → _call 超时。类级共享后任意实例可投递。
    ws = MockWS()
    api_a = QQAPI_list(ws)   # ws 层持有的实例
    api_b = QQAPI_list(ws)   # 其他调用方 new 的实例

    async def run():
        task = asyncio.create_task(api_b._call("send_group_msg", {"group_id": "1"}, timeout=3))
        await asyncio.sleep(0.05)
        echo = ws.sent[-1]["echo"]
        # ws 层（持有 api_a）收到响应，用 api_a.dispatch_response 投递
        ws.api = api_a
        ws.deliver(ws.ok({"message_id": 888}))
        return await task

    ok, data, msg = asyncio.run(run())
    check("实例 B 的调用被实例 A 投递成功", ok and data["message_id"] == 888, (ok, data, msg))
    check("类级 pending 清理", QQAPI_list._pending == {})


def test_call_echo_match():
    print("\n[1] _call 成功：echo 匹配")
    ws, api = make_api()

    async def run():
        task = asyncio.create_task(api._call("get_group_info", {"group_id": "123"}, timeout=5))
        await asyncio.sleep(0.05)  # 让 _call 先发送
        # 模拟 ws 层收到响应并投递
        ws.deliver(ws.ok({"group_id": "123", "group_name": "测试群"}))
        return await task

    ok, data, msg = asyncio.run(run())
    check("调用成功", ok and data["group_name"] == "测试群", (ok, data, msg))
    check("请求含 echo", "echo" in ws.sent[0] and ws.sent[0]["action"] == "get_group_info")
    check("echo 已清理", QQAPI_list._pending == {})


def test_call_failed_response():
    print("\n[2] _call 失败响应")
    ws, api = make_api()

    async def run():
        task = asyncio.create_task(api._call("get_group_info", {}, timeout=5))
        await asyncio.sleep(0.05)
        ws.deliver(ws.fail("权限不足"))
        return await task

    ok, data, msg = asyncio.run(run())
    check("失败返回 (False, None, msg)", (not ok) and data is None and msg == "权限不足", (ok, data, msg))
    check("pending 清理", QQAPI_list._pending == {})


def test_call_timeout():
    print("\n[3] _call 超时")
    ws, api = make_api()

    async def run():
        return await api._call("get_group_info", {}, timeout=0.15)

    ok, data, msg = asyncio.run(run())
    check("超时返回失败", (not ok) and "超时" in msg, (ok, data, msg))
    check("pending 清理", QQAPI_list._pending == {})


def test_unmatched_echo_safe():
    print("\n[4] 未匹配 echo 投递无副作用")
    ws, api = make_api()
    api.dispatch_response("no-such-echo", {"status": "ok"})
    check("未匹配 echo 不崩溃", QQAPI_list._pending == {})


def test_api_wrappers():
    print("\n[5] API 封装：参数与返回值")
    ws, api = make_api()

    async def run():
        # get_group_list：成功返回群号列表
        t1 = asyncio.create_task(api.get_group_list())
        await asyncio.sleep(0.05)
        ws.deliver(ws.ok([{"group_id": "111"}, {"group_id": "222"}]))
        groups = await t1

        # get_group_member_list：成功返回成员数组
        t2 = asyncio.create_task(api.get_group_member_list("111"))
        await asyncio.sleep(0.05)
        ws.deliver(ws.ok([{"user_id": "1", "role": "owner"}]))
        members = await t2

        # get_group_member_info：成功返回 dict
        t3 = asyncio.create_task(api.get_group_member_info("111", "1"))
        await asyncio.sleep(0.05)
        ws.deliver(ws.ok({"user_id": "1", "role": "owner", "card": "x"}))
        info = await t3

        # set_group_kick_member：成功返回 True
        t4 = asyncio.create_task(api.set_group_kick_member("111", "999"))
        await asyncio.sleep(0.05)
        ws.deliver(ws.ok({}))
        kicked = await t4

        # get_group_info 失败返回 {}
        t5 = asyncio.create_task(api.get_group_info("111"))
        await asyncio.sleep(0.05)
        ws.deliver(ws.fail("群不存在"))
        info_fail = await t5
        return groups, members, info, kicked, info_fail

    groups, members, info, kicked, info_fail = asyncio.run(run())
    check("get_group_list 返回群号列表", groups == ["111", "222"], str(groups))
    check("get_group_member_list 返回成员数组", members and members[0]["role"] == "owner", str(members))
    check("get_group_member_info 返回 dict", info.get("card") == "x", str(info))
    check("set_group_kick_member 成功返回 True", kicked is True)
    check("get_group_info 失败返回空 dict", info_fail == {})

    # 校验 kick 请求参数
    kick_payload = ws.sent[3]
    check("kick 参数正确", kick_payload["action"] == "set_group_kick_members"
          and kick_payload["params"]["group_id"] == "111"
          and kick_payload["params"]["user_id"] == ["999"], str(kick_payload))


def test_call_api_generic():
    print("\n[6] call_api 通用入口")
    ws, api = make_api()

    async def run():
        t = asyncio.create_task(api.call_api("get_group_member_list", {"group_id": "1"}))
        await asyncio.sleep(0.05)
        ws.deliver(ws.ok([{"user_id": "1"}]))
        return await t

    data = asyncio.run(run())
    check("call_api 返回 data", isinstance(data, list) and len(data) == 1, str(data))


if __name__ == "__main__":
    test_call_echo_match()
    test_cross_instance_response()
    test_call_failed_response()
    test_call_timeout()
    test_unmatched_echo_safe()
    test_api_wrappers()
    test_call_api_generic()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
