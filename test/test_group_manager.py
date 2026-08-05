"""
群管 app 测试：入群引导 / 观察期 / 段位状态机 / 自动同意 / 命令

运行: uv run python test/test_group_manager.py
"""
import asyncio
import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import runtime
from app.core.member_store import MemberStore
from app.group_manager.service import GroupManagerService
from app.group_manager import config as gm_config

# 测试隔离：不依赖真实 config/group_manager.yml（用户可能修改），强制使用默认配置
gm_config._config = dict(gm_config.DEFAULTS)

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


class FakeAPI:
    """mock API：记录调用"""
    def __init__(self):
        self.messages = []
        self.kicked = []
        self.approved = []
        self.member_infos = {}   # user_id -> dict（存在=是群成员）

    async def send_group_message(self, group_id, text):
        self.messages.append(("group", group_id, text))
        return "msg-123"   # 模拟返回 message_id

    async def send_at_group_message(self, group_id, user_id, text):
        self.messages.append(("at", group_id, text, user_id))

    async def set_group_kick_member(self, group_id, user_id, reject_add_request=False):
        self.kicked.append((group_id, user_id))
        return True

    async def set_group_add_request(self, flag, approve):
        self.approved.append((flag, approve))
        return True

    async def get_group_member_info(self, group_id, user_id, no_cache=False):
        if user_id in self.member_infos:
            return self.member_infos[user_id]
        return {}

    async def get_group_member_list(self, group_id):
        return []


def make_svc():
    """独立 MemberStore + 独立 service 实例（不污染全局单例与真实库）"""
    tmp = tempfile.mkdtemp(prefix="gm_test_")
    store = MemberStore(os.path.join(tmp, "m.db"))
    svc = GroupManagerService()
    svc.store = store
    return svc, store


def test_config_defaults():
    print("\n[1] 配置默认值")
    cfg = gm_config.get()
    check("默认开启", cfg["enabled"] is True)
    check("观察期默认 10 分钟", cfg["observe_minutes"] == 10)
    check("自动同意默认开启且仅授权群", cfg["auto_approve"] is True and cfg["auto_approve_scope"] == "authorized")


def test_member_join_flow():
    print("\n[2] 入群引导：记录 + 欢迎消息 + 观察期 + 段位询问")
    svc, store = make_svc()
    api = FakeAPI()
    runtime.set_api(api)

    class Ev:
        group_id = "g1"
        user_id = "u9"
        raw_message = None
        data = {"group_id": "g1", "user_id": "u9", "message_type": "group"}

    from app.core.tasks import task_scheduler

    async def scenario():
        await svc.on_member_join(Ev())
        return task_scheduler.active()

    active = asyncio.run(scenario())

    m = store.get_member("g1", "u9")
    check("成员已记录", m is not None and m["join_time"] is not None)
    check("观察期任务已调度", f"observe_g1_u9" in active, str(active))
    check("欢迎消息已发送", len(api.messages) == 1 and api.messages[0][0] == "group"
          and "u9" in api.messages[0][2] and "10" in api.messages[0][2], str(api.messages))
    check("段位询问状态已置", store.get_extras("g1", "u9").get("flow") == "awaiting_tier")
    check("欢迎消息 id 已记录", store.get_extras("g1", "u9").get("welcome_msg_id") == "msg-123")


def test_observation_kick():
    print("\n[3] 观察期：未发言踢出 / 已发言跳过")
    svc, store = make_svc()
    api = FakeAPI()
    runtime.set_api(api)

    # 未发言成员 → 踢出
    store.record_join("g1", "u1")
    asyncio.run(svc._check_observation("g1", "u1"))
    check("未发言被踢", ("g1", "u1") in api.kicked, str(api.kicked))

    # 已发言成员 → 跳过
    store.record_join("g1", "u2")
    store.record_message("g1", "u2")
    asyncio.run(svc._check_observation("g1", "u2"))
    check("已发言不踢", ("g1", "u2") not in api.kicked, str(api.kicked))


def test_tier_state_machine():
    print("\n[4] 段位状态机：回复欢迎消息 → 登记")
    svc, store = make_svc()
    api = FakeAPI()
    runtime.set_api(api)

    store.record_join("g1", "u5")
    store.set_extras("g1", "u5", {"flow": "awaiting_tier", "welcome_msg_id": "msg-123"})

    def ev(raw, message_segments=None):
        return type("Ev", (), {
            "group_id": "g1", "user_id": "u5", "raw_message": raw,
            "data": {"message": message_segments or []},
        })

    # 未回复欢迎消息（普通发言）→ 不登记
    asyncio.run(svc.handle_tier_reply(ev("钻石")))
    check("普通发言不登记", store.get_extras("g1", "u5").get("tier") is None)

    # 回复了别的消息（reply id 不匹配）→ 不登记
    asyncio.run(svc.handle_tier_reply(ev("钻石", [{"type": "reply", "data": {"id": "999"}}])))
    check("回复其他消息不登记", store.get_extras("g1", "u5").get("tier") is None)

    # 回复欢迎消息（array reply 段匹配）→ 登记
    asyncio.run(svc.handle_tier_reply(ev("钻石", [{"type": "reply", "data": {"id": "msg-123"}}])))
    check("回复欢迎消息登记", store.get_extras("g1", "u5").get("tier") == "钻石")
    check("流程已结束", store.get_extras("g1", "u5").get("flow") == "")
    check("确认消息以 at 发送", len(api.messages) == 1 and api.messages[0][0] == "at"
          and api.messages[0][3] == "u5" and "钻石" in api.messages[0][2], str(api.messages))

    # raw_message 兜底：CQ:reply 码匹配（message_id 为数字）
    api.messages.clear()
    store.record_join("g1", "u6")
    store.set_extras("g1", "u6", {"flow": "awaiting_tier", "welcome_msg_id": "456"})
    ev2 = type("Ev", (), {
        "group_id": "g1", "user_id": "u6",
        "raw_message": "[CQ:reply,id=456] 铂金",
        "data": {"message": []},
    })
    asyncio.run(svc.handle_tier_reply(ev2))
    check("CQ:reply 兜底登记", store.get_extras("g1", "u6").get("tier") == "铂金")

    # get_reply_id 两种来源
    check("get_reply_id 数组段", svc.get_reply_id(type("E", (), {"data": {"message": [{"type": "reply", "data": {"id": "abc"}}]}, "raw_message": ""})()) == "abc")
    check("get_reply_id CQ 码", svc.get_reply_id(type("E", (), {"data": {"message": []}, "raw_message": "[CQ:reply,id=-42] x"})()) == "-42")


def test_auto_approve():
    print("\n[5] 自动同意入群：授权群同意 / 未授权跳过")
    svc, store = make_svc()
    api = FakeAPI()
    runtime.set_api(api)

    class Ev:
        group_id = "gA"
        user_id = "uNew"
        data = {"group_id": "gA", "user_id": "uNew", "sub_type": "add", "flag": "flag1"}

    # patch 权限：gA 已授权
    import app.permission as perm_mod
    old_perm = perm_mod.permission_service
    perm_mod.permission_service = type("Stub", (), {"check_group_authorized": staticmethod(lambda g: g == "gA")})()
    try:
        asyncio.run(svc.handle_group_request(Ev()))
    finally:
        perm_mod.permission_service = old_perm
    check("授权群自动同意", api.approved == [("flag1", True)], str(api.approved))

    # 未授权群跳过
    api.approved.clear()
    class Ev2:
        group_id = "gB"
        user_id = "uNew2"
        data = {"group_id": "gB", "user_id": "uNew2", "sub_type": "add", "flag": "flag2"}
    asyncio.run(svc.handle_group_request(Ev2()))
    check("未授权群跳过", api.approved == [], str(api.approved))

    # 关闭自动同意 → 不处理
    old_cfg = gm_config._config["auto_approve"]
    gm_config._config["auto_approve"] = False
    try:
        asyncio.run(svc.handle_group_request(Ev2()))
    finally:
        gm_config._config["auto_approve"] = old_cfg
    check("关闭后不处理", api.approved == [])


def test_query_and_commands():
    print("\n[6] 查询与命令 handler（含存量成员验证）")
    svc, store = make_svc()
    api = FakeAPI()
    runtime.set_api(api)

    # 有记录成员 → 档案
    store.record_join("g1", "u7", join_time="2026-01-01 08:00:00")
    store.record_message("g1", "u7")
    store.set_extras("g1", "u7", {"tier": "王者"})

    text = asyncio.run(svc.query_member("g1", "u7"))
    check("查询含段位与时间", "王者" in text and "2026-01-01 08:00:00" in text and "最后活跃" in text, text)

    # 无记录 + 真实群成员 → 补记录 + 存量成员文案
    api.member_infos["uOld"] = {"user_id": "uOld", "role": "member"}
    text = asyncio.run(svc.query_member("g1", "uOld"))
    check("存量成员文案", "是本群成员" in text and "暂无活跃/段位记录" in text, text)
    check("存量成员已补记录", store.get_member("g1", "uOld") is not None)

    # 无记录 + 非群成员
    text = asyncio.run(svc.query_member("g1", "uStranger"))
    check("非成员文案", "不是本群成员" in text, text)

    # API 不可用
    runtime.set_api(None)
    text = asyncio.run(svc.query_member("g1", "uStranger"))
    check("API 不可用文案", "无法验证" in text, text)
    runtime.set_api(api)

    check("at 解析", svc.parse_at("[CQ:at,qq=3014617667] 3") == "3014617667")
    check("无 at 返回空", svc.parse_at("普通消息") == "")

    # 命令 handler（patch 全局单例 store 为测试库）
    from app.group_manager.commands import _active_handler, _tier_handler, _parse_target
    from app.group_manager.service import group_manager_service
    old_store = group_manager_service.store
    group_manager_service.store = store
    try:
        msg = {"raw_message": "/active", "group_id": "g1", "user_id": "u7"}
        judge, reply = asyncio.run(_active_handler(None, msg))
        check("/active 输出", judge and "王者" in reply, reply)

        msg2 = {"raw_message": "/tier 88888888", "group_id": "g1", "user_id": "u7"}
        judge, reply = asyncio.run(_tier_handler(None, msg2))
        check("/tier 查询不存在成员", judge and "不是本群成员" in reply, reply)
    finally:
        group_manager_service.store = old_store

    check("_parse_target 缺省自己", _parse_target("/active", "u7") == "u7")
    check("_parse_target 显式 QQ", _parse_target("/active 999", "u7") == "999")
    check("_parse_target @", _parse_target("/active [CQ:at,qq=555]", "u7") == "555")


def test_event_bus_integration():
    print("\n[7] 事件总线集成：订阅 → 分发 → 群管响应")
    # 验证 events 模块已注册订阅（import main 链路）
    from app.core.events import event_bus, EventType, Event
    from app.group_manager import events as gm_events

    check("GROUP_INCREASE 有订阅", event_bus.subscriber_count(EventType.GROUP_INCREASE) >= 1)
    check("GROUP_REQUEST 有订阅", event_bus.subscriber_count(EventType.GROUP_REQUEST) >= 1)
    check("MESSAGE 有订阅", event_bus.subscriber_count(EventType.MESSAGE) >= 1)

    # 完整链路：入群事件 → service（stub runtime api）
    api = FakeAPI()
    runtime.set_api(api)
    svc, store = make_svc()

    from app.group_manager.service import group_manager_service
    old_store = group_manager_service.store
    group_manager_service.store = store
    try:
        class Ev:
            group_id = "g1"
            user_id = "uNew"
            raw_message = None
            data = {"group_id": "g1", "user_id": "uNew", "message_type": "group"}
        asyncio.run(event_bus.emit(Event(type=EventType.GROUP_INCREASE, data=Ev.data)))
        check("事件驱动入群引导", len(api.messages) == 1 and api.messages[0][0] == "group"
              and "uNew" in api.messages[0][2], str(api.messages))
        m = store.get_member("g1", "uNew")
        check("事件驱动成员记录", m is not None and m["extras"].get("flow") == "awaiting_tier")
        from app.core.tasks import task_scheduler
        task_scheduler.cancel("observe_g1_uNew")
    finally:
        group_manager_service.store = old_store
        runtime.set_api(None)


def test_backfill():
    print("\n[8] 存量成员批量补记录（ensure_member 不覆盖）")
    svc, store = make_svc()
    api = FakeAPI()
    runtime.set_api(api)

    # 已有成员（含 extras）不应被覆盖
    store.record_join("g1", "uOld", join_time="2026-01-01 00:00:00")
    store.set_extras("g1", "uOld", {"tier": "王者"})

    # 群成员列表：2 个存量 + 1 个已有
    api.member_infos = {}  # 复用 get_group_member_info 的字典不需要；直接用 get_group_member_list
    class FakeAPI2(FakeAPI):
        async def get_group_member_list(self, group_id):
            return [{"user_id": "uOld"}, {"user_id": "uA"}, {"user_id": "uB"}]
    old_api = runtime.get_api()
    api2 = FakeAPI2()
    runtime.set_api(api2)
    try:
        added, total = asyncio.run(svc.backfill_group("g1"))
    finally:
        runtime.set_api(old_api)
    check("补记录计数", added == 2 and total == 3, str((added, total)))
    check("新增成员已记录", store.get_member("g1", "uA") is not None and store.get_member("g1", "uB") is not None)
    old = store.get_member("g1", "uOld")
    check("已有成员未覆盖", old["join_time"] == "2026-01-01 00:00:00" and old["extras"].get("tier") == "王者", str(old))

    # ensure_member 幂等
    check("ensure_member 幂等", store.ensure_member("g1", "uA") is False)
    check("ensure_member 新增", store.ensure_member("g1", "uC") is True)

    # 命令 handler
    from app.group_manager.commands import _backfill_handler
    from app.group_manager.service import group_manager_service
    old_store = group_manager_service.store
    group_manager_service.store = store
    try:
        judge, reply = asyncio.run(_backfill_handler(None, {"raw_message": "/backfill 111", "group_id": "g", "user_id": "u"}))
        check("/backfill 指定群", judge and "111" in reply and "补记录完成" in reply, reply)
    finally:
        group_manager_service.store = old_store


if __name__ == "__main__":
    test_config_defaults()
    test_member_join_flow()
    test_observation_kick()
    test_tier_state_machine()
    test_auto_approve()
    test_query_and_commands()
    test_event_bus_integration()
    test_backfill()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
