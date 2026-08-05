"""
命令注册中心回归测试（临时脚本，使用独立 registry 与权限 stub，不污染全局状态）

运行: uv run python test_commands.py
"""
import asyncio
import sys

from app.core.commands.model import Command
from app.core.commands.registry import CommandRegistry
from app.permission.constants import LEVEL_SYSTEM, LEVEL_OWNER, LEVEL_ADMIN, LEVEL_NONE

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


class FakeWS:
    """fake websocket：记录发送的消息（解析为 dict）"""
    def __init__(self):
        self.sent = []

    async def send(self, data):
        import json
        self.sent.append(json.loads(data))


class StubPerm:
    """权限 stub：可控的 check_user_permission 结果"""
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    def check_user_permission(self, group_id, user_id, required_level):
        self.calls.append((group_id, user_id, required_level))
        return self.allowed


def msg(raw, group="g1", user="u1"):
    return {"raw_message": raw, "group_id": group, "user_id": user}


def test_register_and_conflict():
    print("\n[1] 注册与冲突检测")

    async def h(ws, m):
        return True, "ok"

    r = CommandRegistry()
    check("首次注册成功", r.register(Command(name="/a", handler=h, app_name="A", aliases=["a"])))
    check("别名可匹配", r.match("a xyz").name == "/a")
    check("主名可匹配", r.match("/a").name == "/a")

    # 冲突：同名
    check("同名注册被拒", not r.register(Command(name="/a", handler=h, app_name="B")))
    check("冲突不覆盖原命令", r.match("/a").app_name == "A")
    # 冲突：别名占用
    check("占用别名的注册被拒", not r.register(Command(name="/b", handler=h, app_name="B", aliases=["a"])))
    check("冲突后 /b 未注册", r.match("/b") is None)


def test_match():
    print("\n[2] 首词匹配")
    r = CommandRegistry()

    async def h(ws, m):
        return True, "ok"

    r.register(Command(name="/sub", handler=h, aliases=["subscribe_group"]))
    check("多行命令首词匹配", r.match("subscribe_group 123\nstarttime now\nendtime 30").name == "/sub")
    check("斜杠主名匹配", r.match("/sub").name == "/sub")
    check("未命中返回 None", r.match("随便说说") is None)
    check("空消息返回 None", r.match("") is None)


def test_dispatch_auth_and_reply():
    print("\n[3] 分发：执行 / 鉴权 / 未命中")
    r = CommandRegistry()

    async def h(ws, m):
        return True, f"执行了:{m['raw_message']}"

    r.register(Command(name="/ok", handler=h, required_level=LEVEL_NONE))

    # 命中 + 回复
    ws = FakeWS()
    handled = asyncio.run(r.dispatch(ws, msg("/ok 参数")))
    check("命中返回 True", handled)
    text = ws.sent[0]["params"]["message"][0]["data"]["text"]
    check("回复已发送", len(ws.sent) == 1 and "执行了:/ok 参数" in text, str(ws.sent))

    # 未命中
    ws = FakeWS()
    handled = asyncio.run(r.dispatch(ws, msg("不是命令")))
    check("未命中返回 False 且不回复", not handled and ws.sent == [])

    # 鉴权：权限不足（stub allowed=False）→ 统一回复
    import sys
    registry_mod = sys.modules["app.core.commands.registry"]
    old_perm = registry_mod.permission_service
    registry_mod.permission_service = StubPerm(allowed=False)
    try:
        r2 = CommandRegistry()
        r2.register(Command(name="/need3", handler=h, required_level=LEVEL_ADMIN))
        ws = FakeWS()
        handled = asyncio.run(r2.dispatch(ws, msg("/need3")))
        check("权限不足返回 True（已处理）", handled)
        text = ws.sent[0]["params"]["message"][0]["data"]["text"]
        check("权限不足统一回复", len(ws.sent) == 1 and "权限不足" in text, text)
    finally:
        registry_mod.permission_service = old_perm


def test_help_filter_and_group():
    print("\n[4] 帮助：分组 + 权限过滤 + 详情")
    r = CommandRegistry()

    async def h(ws, m):
        return True, None

    r.register(Command(name="/admin_cmd", handler=h, required_level=LEVEL_SYSTEM, app_name="权限系统", description="管理员命令", usage="<x>"))
    r.register(Command(name="/user_cmd", handler=h, required_level=LEVEL_ADMIN, app_name="定时喊话", description="用户命令"))
    r.register(Command(name="/open", handler=h, required_level=LEVEL_NONE, app_name="公共", description="开放命令"))

    # 管理员视角：全看到
    import sys
    registry_mod = sys.modules["app.core.commands.registry"]
    old_perm = registry_mod.permission_service
    registry_mod.permission_service = StubPerm(allowed=True)
    try:
        text = r.help_text("g1", "admin", "")
        check("管理员看到所有命令", all(x in text for x in ("/admin_cmd", "/user_cmd", "/open")))
        check("按 app 分组", "🔹 权限系统" in text and "🔹 定时喊话" in text)
        check("显示权限级别", "系统管理员" in text)
    finally:
        registry_mod.permission_service = old_perm

    # 3 级视角：看不到管理员命令（stub 对 1 级要求返回 False）
    class StubPermLevel:
        def check_user_permission(self, g, u, level):
            return level >= LEVEL_ADMIN  # 仅 3 级及以下需求放行（3/4 可见）
    registry_mod.permission_service = StubPermLevel()
    try:
        text = r.help_text("g1", "u3", "")
        check("3级看不到管理员命令", "/admin_cmd" not in text)
        check("3级看到本级别与开放命令", "/user_cmd" in text and "/open" in text)
    finally:
        registry_mod.permission_service = old_perm

    # 详情：含用法与权限（stub 管理员视角）
    registry_mod.permission_service = StubPerm(allowed=True)
    try:
        detail = r.help_text("g1", "admin", "/admin_cmd")
        check("详情含用法", "用法: <x>" in detail and "管理员命令" in detail, detail)
        check("详情含权限级别", "需要权限: 系统管理员" in detail, detail)
    finally:
        registry_mod.permission_service = old_perm
    # 不存在命令
    check("未知命令提示", "未找到命令" in r.help_text("g1", "admin", "/nope"))


def test_handler_exception_handled():
    print("\n[5] handler 异常不中断分发")
    r = CommandRegistry()

    async def boom(ws, m):
        raise RuntimeError("boom")

    r.register(Command(name="/boom", handler=boom, required_level=LEVEL_NONE))
    ws = FakeWS()
    handled = asyncio.run(r.dispatch(ws, msg("/boom")))
    check("异常命令返回 True（已处理）", handled)
    text = ws.sent[0]["params"]["message"][0]["data"]["text"]
    check("异常提示已回复", len(ws.sent) == 1 and "执行出错" in text, text)


if __name__ == "__main__":
    test_register_and_conflict()
    test_match()
    test_dispatch_auth_and_reply()
    test_help_filter_and_group()
    test_handler_exception_handled()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
