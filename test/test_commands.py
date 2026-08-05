"""
命令注册中心回归测试（临时脚本，使用独立 registry 与权限 stub，不污染全局状态）

运行: uv run python test/test_commands.py
"""
import asyncio
import os
import sys

# 确保从项目根可导入 app.*（脚本位于 test/ 子目录）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.commands.model import Command
from app.core.commands.registry import CommandRegistry
from app.core.permission.constants import LEVEL_SYSTEM, LEVEL_OWNER, LEVEL_ADMIN, LEVEL_NONE

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


class FakeRuntimeAPI:
    """registry._reply 经 runtime.get_api() 发送消息的 fake"""
    def __init__(self, ws):
        self.ws = ws

    async def send_group_message(self, group_id, text):
        import json
        await self.ws.send(json.dumps({
            "action": "send_group_msg",
            "params": {"group_id": group_id, "message": [{"type": "text", "data": {"text": text}}]},
        }))
        return 1


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

    # 命中 + 回复（registry._reply 走 runtime API）
    from app.core.runtime import set_api
    ws = FakeWS()
    set_api(FakeRuntimeAPI(ws))
    try:
        handled = asyncio.run(r.dispatch(ws, msg("/ok 参数")))
        check("命中返回 True", handled)
        text = ws.sent[0]["params"]["message"][0]["data"]["text"]
        check("回复已发送", len(ws.sent) == 1 and "执行了:/ok 参数" in text, str(ws.sent))

        # 未命中
        ws = FakeWS()
        set_api(FakeRuntimeAPI(ws))
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
            set_api(FakeRuntimeAPI(ws))
            handled = asyncio.run(r2.dispatch(ws, msg("/need3")))
            check("权限不足返回 True（已处理）", handled)
            text = ws.sent[0]["params"]["message"][0]["data"]["text"]
            check("权限不足统一回复", len(ws.sent) == 1 and "权限不足" in text, text)
        finally:
            registry_mod.permission_service = old_perm
    finally:
        set_api(None)


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
    from app.core.runtime import set_api
    ws = FakeWS()
    set_api(FakeRuntimeAPI(ws))
    try:
        handled = asyncio.run(r.dispatch(ws, msg("/boom")))
        check("异常命令返回 True（已处理）", handled)
        text = ws.sent[0]["params"]["message"][0]["data"]["text"]
        check("异常提示已回复", len(ws.sent) == 1 and "执行出错" in text, text)
    finally:
        set_api(None)


def test_validation_rejects_bad_commands():
    print("\n[6] 格式校验：拒绝非法命令定义")
    r = CommandRegistry()

    async def h(ws, m):
        return True, None

    check("空命令名被拒", not r.register(Command(name="", handler=h)))
    check("含空格命令名被拒", not r.register(Command(name="/bad name", handler=h)))
    check("handler 不可调用被拒", not r.register(Command(name="/no_handler", handler="not_callable")))
    check("非法级别被拒", not r.register(Command(name="/bad_level", handler=h, required_level=99)))
    check("子命令缺说明被拒", not r.register(Command(
        name="/bad_sub", handler=h, sub_commands={"添加": ""})))
    check("合法命令注册成功", r.register(Command(name="/good", handler=h, required_level=LEVEL_NONE)))
    check("被拒命令未进入注册表", r.match("/bad name") is None and r.match("/no_handler") is None)
    check("被拒记录进入 audit.conflicts", any(c["name"] == "/bad_level" for c in r.audit()["conflicts"]))


def test_audit_and_prefix_conflict():
    print("\n[7] 审计：统计 / 前缀重叠 / 报告文本")
    r = CommandRegistry()

    async def h(ws, m):
        return True, None

    r.register(Command(name="/定时喊话", handler=h, app_name="A", required_level=LEVEL_NONE))
    r.register(Command(name="/list_user", handler=h, app_name="B", aliases=["list_user"], required_level=LEVEL_NONE))

    # 前缀重叠：/定时 与 /定时喊话 互为前缀
    r.register(Command(name="/定时", handler=h, app_name="C", required_level=LEVEL_NONE))

    a = r.audit()
    check("统计总数", a["total"] == 3, str(a))
    check("按 app 统计", a["apps"].get("A") == 1 and a["apps"].get("B") == 1)
    check("无注册冲突", a["conflicts"] == [])
    check("检测到跨 app 前缀冲突", any(
        ("/定时" in ka and "/定时喊话" in kb) or ("/定时" in kb and "/定时喊话" in ka)
        for ka, kb, cross in a["prefix_conflicts"] if cross
    ), str(a["prefix_conflicts"]))

    report = r.report_text()
    check("报告含统计", "3 条命令" in report)
    check("报告含无冲突", "无注册冲突" in report)
    check("报告含跨 app 冲突标题", "跨 app 前缀冲突" in report)

    # 同 app 内前缀重叠（有意的关联命令，仅提示）
    r.register(Command(name="/list_user2", handler=h, app_name="B", required_level=LEVEL_NONE))
    report2 = r.report_text()
    check("报告含同 app 提示标题", "同 app 前缀重叠" in report2)

    # 冲突后 audit 反映
    r.register(Command(name="/定时喊话", handler=h, app_name="D"))  # 同名被拒
    a2 = r.audit()
    check("同名冲突进入 audit.conflicts", len(a2["conflicts"]) == 1 and a2["conflicts"][0]["name"] == "/定时喊话")
    check("冲突后报告不再说无冲突", "无注册冲突" not in r.report_text())


def test_help_sorted_and_aligned():
    print("\n[8] 帮助排序与对齐")
    r = CommandRegistry()

    async def h(ws, m):
        return True, None

    # 乱序注册：不同级别 + 同级不同名
    r.register(Command(name="/z_level3", handler=h, required_level=LEVEL_ADMIN, app_name="A", description="d3"))
    r.register(Command(name="/a_level1", handler=h, required_level=LEVEL_SYSTEM, app_name="A", description="d1", usage="<x>"))
    r.register(Command(name="/m_level2", handler=h, required_level=LEVEL_OWNER, app_name="A", description="d2"))
    r.register(Command(name="/b_level3", handler=h, required_level=LEVEL_ADMIN, app_name="A", description="d3b"))
    r.register(Command(name="/a_level3", handler=h, required_level=LEVEL_ADMIN, app_name="A", description="d3a"))

    import sys
    registry_mod = sys.modules["app.core.commands.registry"]
    old = registry_mod.permission_service
    registry_mod.permission_service = StubPerm(allowed=True)
    try:
        text = r.help_text("g", "u", "")
        # 排序：先权限级别（1→2→3），同级按名称
        i1 = text.index("/a_level1")
        i2 = text.index("/m_level2")
        i3 = text.index("/z_level3")
        check("组内按权限级别排序", i1 < i2 < i3, text)
        i_a = text.index("/a_level3")
        i_b = text.index("/b_level3")
        check("同级按名称排序", i_a < i_b < i3, text)
        # 对齐：命令列 ljust 后分隔符位置一致
        lines = [l for l in text.splitlines() if l.startswith("  /")]
        pos = [l.index(" - ") for l in lines]
        check("命令列对齐", len(set(pos)) == 1, str(pos))
    finally:
        registry_mod.permission_service = old


def test_help_detail_and_example():
    print("\n[9] /help <命令> 详细说明与示例")
    r = CommandRegistry()

    async def h(ws, m):
        return True, None

    r.register(Command(
        name="/sub_group", handler=h, required_level=LEVEL_SYSTEM, app_name="A",
        description="登记授权群组", usage="<群号> <天数>",
        detail="简单版群授权：立即生效。\n获权用户缺省为执行者。",
        example="/sub_group 123456789 30\n# 授权 30 天",
    ))
    r.register(Command(
        name="/plain", handler=h, required_level=LEVEL_NONE, app_name="A", description="无详情命令",
    ))

    import sys
    registry_mod = sys.modules["app.core.commands.registry"]
    old = registry_mod.permission_service
    registry_mod.permission_service = StubPerm(allowed=True)
    try:
        detail = r.help_text("g", "u", "/sub_group")
        check("详情含详细说明标题", "详细说明" in detail, detail)
        check("详情含详细说明多行内容", "简单版群授权：立即生效" in detail and "获权用户缺省为执行者" in detail)
        check("详情含示例标题", "示例" in detail)
        check("详情含示例内容", "/sub_group 123456789 30" in detail and "# 授权 30 天" in detail)
        plain = r.help_text("g", "u", "/plain")
        check("无 detail 不显示详细说明", "详细说明" not in plain)
        check("无 example 不显示示例", "示例" not in plain)
    finally:
        registry_mod.permission_service = old


if __name__ == "__main__":
    test_register_and_conflict()
    test_match()
    test_dispatch_auth_and_reply()
    test_help_filter_and_group()
    test_handler_exception_handled()
    test_validation_rejects_bad_commands()
    test_audit_and_prefix_conflict()
    test_help_sorted_and_aligned()
    test_help_detail_and_example()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
