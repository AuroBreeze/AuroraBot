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
        self.member_roles = {}   # user_id -> role（owner/admin/member）

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
        return [{"user_id": uid, "role": role} for uid, role in self.member_roles.items()]


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
    check("不活跃踢人默认关闭", cfg["inactive_kick_enabled"] is False)
    check("不活跃阈值默认 7 天", cfg["inactive_kick_days"] == 7)


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
    import app.core.permission as perm_mod
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


def test_auto_backfill_pending():
    print("\n[9] 自动补记录：未处理群自动补一次，已处理群跳过")
    svc, store = make_svc()

    class FakeAPI3(FakeAPI):
        def __init__(self):
            super().__init__()
            self.member_lists = {"gA": [{"user_id": "u1"}, {"user_id": "u2"}], "gB": [{"user_id": "u3"}]}
            self.group_list_calls = 0
            self.member_list_calls = []

        async def get_group_list(self):
            self.group_list_calls += 1
            return list(self.member_lists.keys())

        async def get_group_member_list(self, group_id):
            self.member_list_calls.append(group_id)
            return self.member_lists.get(group_id, [])

    api3 = FakeAPI3()
    runtime.set_api(api3)

    # patch 权限：gA/gB 已授权
    import app.core.permission as perm_mod
    old_perm = perm_mod.permission_service
    perm_mod.permission_service = type("Stub", (), {"check_group_authorized": staticmethod(lambda g: True)})()

    # 单例 store 替换为测试库
    from app.group_manager.service import group_manager_service
    old_store = group_manager_service.store
    group_manager_service.store = store
    try:
        # 第一次：两个未处理群都被补 + 标记
        asyncio.run(svc.auto_backfill_pending())
        check("未处理群全部补齐", store.get_member("gA", "u1") is not None and store.get_member("gB", "u3") is not None)
        check("已标记", store.is_backfilled("gA") and store.is_backfilled("gB"))

        # 第二次：已处理群跳过（不再拉取成员列表）
        api3.member_list_calls.clear()
        asyncio.run(svc.auto_backfill_pending())
        check("已处理群跳过", api3.member_list_calls == [], str(api3.member_list_calls))
    finally:
        group_manager_service.store = old_store
        perm_mod.permission_service = old_perm

    # 手动 /backfill 也会标记
    svc2, store2 = make_svc()
    runtime.set_api(FakeAPI3())
    asyncio.run(svc2.backfill_group("gX"))
    check("手动 backfill 后标记", store2.is_backfilled("gX"))


def test_members_list():
    print("\n[10] 批量成员信息 /members（加入/活跃/段位/段位时间 + 分页）")
    svc, store = make_svc()

    # 造 25 个成员
    for i in range(1, 26):
        store.record_join("g1", f"u{i:02d}", join_time=f"2026-01-{(i % 28) + 1:02d} 08:00:00")
        if i % 2 == 0:
            store.record_message("g1", f"u{i:02d}")
    store.set_extras("g1", "u02", {"tier": "王者", "tier_time": "2026-02-01 09:30:00"})
    store.set_extras("g1", "u01", {"tier": "钻石"})  # 有段位无登记时间

    text = svc.list_members("g1", 1)
    check("列表含标题与分页", "第 1/2 页" in text and "本群 25 人" in text, text[:60])
    check("含加入/活跃/段位/登记字段", "加入:" in text and "活跃:" in text and "段位:" in text and "登记:" in text)
    check("段位与登记时间显示", "段位:王者 登记:02-01 09:30" in text, text)
    check("段位无登记时间显示 -", "段位:钻石 登记:-" in text, text)
    check("未登记段位显示 -", "段位:-" in text)
    check("分页提示", "/members 2 查看下一页" in text)

    text2 = svc.list_members("g1", 2)
    check("第二页", "第 2/2 页" in text2 and "u24" in text2 and "u25" in text2, text2[:100])

    text3 = svc.list_members("g1", 3)
    check("越界提示", "页码越界" in text3, text3)

    # 无记录群
    text4 = svc.list_members("gEmpty")
    check("无记录提示补记录", "暂无成员记录" in text4 and "/backfill" in text4, text4)

    # 段位登记时间已记录（handle_tier_reply）
    api = FakeAPI()
    runtime.set_api(api)
    store.record_join("g1", "uNew")
    store.set_extras("g1", "uNew", {"flow": "awaiting_tier", "welcome_msg_id": "msg-123"})
    ev = type("E", (), {"group_id": "g1", "user_id": "uNew",
                        "raw_message": "铂金", "data": {"message": [{"type": "reply", "data": {"id": "msg-123"}}]}})()
    asyncio.run(svc.handle_tier_reply(ev))
    extras = store.get_extras("g1", "uNew")
    check("段位登记时间已记录", extras.get("tier") == "铂金" and extras.get("tier_time"), str(extras))
    check("登记时间格式正确", len(str(extras.get("tier_time"))) == 19, str(extras.get("tier_time")))

    # 命令 handler
    from app.group_manager.commands import _members_handler
    from app.group_manager.service import group_manager_service
    old_store = group_manager_service.store
    group_manager_service.store = store
    try:
        judge, reply = asyncio.run(_members_handler(None, {"raw_message": "/members", "group_id": "g1", "user_id": "u"}))
        check("/members 命令输出", judge and "群成员档案" in reply, reply[:60])
    finally:
        group_manager_service.store = old_store


def test_never_kick_self():
    print("\n[11] 不踢机器人自己：入群引导跳过 + 观察期不踢")
    from app.core.tasks import task_scheduler
    svc, store = make_svc()
    api = FakeAPI()
    runtime.set_api(api)
    runtime.set_self_id("BOT01")

    try:
        # bot 自己入群：不引导（无欢迎消息/无观察期/不记录状态机）
        class Ev:
            group_id = "g1"
            user_id = "BOT01"
            raw_message = None
            data = {"group_id": "g1", "user_id": "BOT01"}
        asyncio.run(svc.on_member_join(Ev()))
        check("bot 入群不发送欢迎", api.messages == [], str(api.messages))
        check("bot 入群无观察期任务", all(not t.startswith("observe_") for t in task_scheduler.active()), str(task_scheduler.active()))
        check("bot 入群无段位询问状态", store.get_extras("g1", "BOT01") == {})

        # 观察期检查到 bot：不踢
        store.record_join("g1", "BOT01")  # 即使有记录
        asyncio.run(svc._check_observation("g1", "BOT01"))
        check("观察期不踢 bot", api.kicked == [], str(api.kicked))

        # 普通成员仍正常踢
        store.record_join("g1", "uHuman")
        asyncio.run(svc._check_observation("g1", "uHuman"))
        check("普通成员仍会被踢", ("g1", "uHuman") in api.kicked, str(api.kicked))
    finally:
        runtime.set_self_id("")
        runtime.set_api(None)


def test_inactive_kick():
    print("\n[12] 不活跃自动踢人（开关默认关闭，开启后 7 天可配 + 排除名单 + 踢前提醒）")
    from datetime import datetime, timedelta
    from app.core import timeutil
    gm_config._config["inactive_kick_enabled"] = True  # 测试内显式开启
    svc, store = make_svc()
    now = timeutil.bj_now()

    def ts(days_ago):
        return (now - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")

    # 成员：uOld 10 天未发言(超期) / uRmd 6 天未发言(剩1天提醒) / uNew 2 天 / uNoActive 无活跃按入群 9 天前
    store.record_join("g1", "uOld", join_time=ts(20))
    store.record_message("g1", "uOld")
    store.get_member("g1", "uOld")  # last_active = now
    # 覆盖 last_active 为 10 天前：直接 set 需要操作——用 record_message 后改？简化：重新构造
    # 用 ensure + set 不可行，直接操作 store 连接
    conn = store._get_connection()
    conn.execute("UPDATE group_members SET last_active=? WHERE group_id='g1' AND user_id='uOld'", (ts(10),))
    store.record_join("g1", "uRmd", join_time=ts(6))
    store.record_join("g1", "uNew", join_time=ts(2))
    store.record_join("g1", "uNoActive", join_time=ts(9))   # 无活跃记录，按入群 9 天超期
    store.record_join("g1", "uOwner", join_time=ts(15))     # 群主，跳过
    store.record_join("g1", "uAdmin", join_time=ts(15))     # 管理员，跳过
    store.record_join("g1", "uVip", join_time=ts(15))       # 有权限用户，跳过
    conn.commit()

    class FakeInactiveAPI(FakeAPI):
        async def get_group_list(self):
            return ["g1"]

        async def get_group_member_list(self, group_id):
            return [
                {"user_id": "uOwner", "role": "owner"},
                {"user_id": "uAdmin", "role": "admin"},
                {"user_id": "uVip", "role": "member"},
                {"user_id": "uOld", "role": "member"},
                {"user_id": "uRmd", "role": "member"},
                {"user_id": "uNew", "role": "member"},
                {"user_id": "uNoActive", "role": "member"},
            ]

    api = FakeInactiveAPI()
    runtime.set_api(api)
    runtime.set_self_id("BOTX")

    import app.core.permission as perm_mod
    old_perm = perm_mod.permission_service
    # 有权限用户 uVip 判定为有权限；其余无
    class StubPerm:
        def check_group_authorized(self, g):
            return True

        def check_user_permission(self, g, u, level):
            return u == "uVip"

    perm_mod.permission_service = StubPerm()

    from app.group_manager.service import group_manager_service
    old_store = group_manager_service.store
    group_manager_service.store = store
    try:
        asyncio.run(svc.scan_inactive_members())
    finally:
        group_manager_service.store = old_store
        perm_mod.permission_service = old_perm

    kicked = [k[1] for k in api.kicked]
    check("超期成员被踢（有活跃记录）", "uOld" in kicked, str(kicked))
    check("无活跃记录按入群超期被踢", "uNoActive" in kicked, str(kicked))
    check("未超期不踢", "uNew" not in kicked and "uRmd" not in kicked, str(kicked))
    check("群主跳过", "uOwner" not in kicked, str(kicked))
    check("管理员跳过", "uAdmin" not in kicked, str(kicked))
    check("有权限用户跳过", "uVip" not in kicked, str(kicked))
    check("bot 跳过", "BOTX" not in kicked)

    # 踢前提醒：uRmd（6 天，剩 1 天）
    reminds = [m for m in api.messages if m[0] == "at" and m[3] == "uRmd"]
    check("踢前提醒已发送", len(reminds) == 1 and "1 天" in reminds[0][2], str(reminds))
    check("提醒当天不重复", store.get_extras("g1", "uRmd").get("inactive_reminded") == now.strftime("%Y-%m-%d"))

    # 再扫描一次：uRmd 不再提醒
    api.messages.clear()
    asyncio.run(svc.scan_inactive_members())
    check("提醒不重复", len(api.messages) == 0, str(api.messages))


def test_inactive_list_and_kick():
    print("\n[15] 不活跃列表 + 批量踢人（/inactive /kick）")
    import pytz
    from datetime import datetime, timedelta
    from app.core.runtime import set_api, set_self_id

    svc, store = make_svc()
    api = FakeAPI()
    api.member_roles = {
        "1001": "member", "1002": "member", "1003": "member",
        "1004": "member", "1005": "admin", "9001": "owner",
    }
    set_api(api)
    set_self_id("9001")
    tz = pytz.timezone("Asia/Shanghai")
    now = datetime.now(tz)
    fmt = lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S")
    # 无发言记录 → 按入群时间兜底计未活跃天数（bot 9001 不应出现在列表）
    store.record_join("g1", "1001", fmt(now - timedelta(days=15)))
    store.record_join("g1", "1002", fmt(now - timedelta(days=9)))
    store.record_join("g1", "1003", fmt(now - timedelta(days=3)))
    store.record_join("g1", "1004", fmt(now - timedelta(days=20)))
    store.record_join("g1", "1005", fmt(now - timedelta(days=12)))
    store.record_join("g1", "9001", fmt(now - timedelta(days=30)))
    store.record_message("g1", "1002")  # 有活跃记录（今天）→ 0 天，应被过滤

    text = svc.list_inactive_members("g1", 7, 1)
    check("列表标题含总数与分页", "共 3 人" in text and "第 1/1 页" in text, text)
    check("降序：最不活跃在前", text.index("1004") < text.index("1001") < text.index("1005"), text)
    check("每行 @ 成员", "[CQ:at,qq=1004]" in text and "[CQ:at,qq=1001]" in text, text)
    check("显示未活跃天数", "未活跃 20 天" in text and "未活跃 15 天" in text, text)
    check("今日活跃成员被过滤", "1002" not in text.splitlines()[1:] and "未活跃 0 天" not in text, text)
    check("机器人自己不出现在列表", "9001" not in text, text)

    # 分页：再入 12 人 → 共 16 人 → 2 页
    for i in range(12):
        store.record_join("g1", f"70{i:02d}", fmt(now - timedelta(days=10)))
    # 未指定页码 → 全部列出
    text_all = svc.list_inactive_members("g1", 7)
    check("默认全部列出：标题无页码", "第" not in text_all.splitlines()[0] and "共 15 人" in text_all.splitlines()[0], text_all.splitlines()[0])
    check("默认全部列出：含全部成员", "1." in text_all and "15." in text_all, text_all)
    text_p1 = svc.list_inactive_members("g1", 7, 1)
    check("分页标题 第1/2页", "第 1/2 页" in text_p1, text_p1)
    text_p2 = svc.list_inactive_members("g1", 7, 2)
    check("第2页有序号", "11." in text_p2, text_p2)
    check("页码越界回退", "第 99/2 页" not in svc.list_inactive_members("g1", 7, 99), svc.list_inactive_members("g1", 7, 99))

    async def run_kick(raw):
        return await svc.kick_members("g1", "1001", raw)

    t = asyncio.run(run_kick("/kick 1 2"))
    check("序号踢出", "已移出 2 人" in t and "1004" in t and "1001" in t, t)
    check("踢出调用记录", ("g1", "1004") in api.kicked and ("g1", "1001") in api.kicked, str(api.kicked))
    t = asyncio.run(run_kick("/kick [CQ:at,qq=1003]"))
    check("@ 踢出", "已移出 1 人" in t and "1003" in t, t)
    t = asyncio.run(run_kick("/kick 99999999"))
    check("非成员 QQ 号跳过", "不在群成员" in t, t)
    t = asyncio.run(run_kick("/kick 1005 9001"))
    check("管理员与机器人跳过", "群主/管理员" in t and "机器人自己" in t, t)
    t = asyncio.run(run_kick("/kick"))
    check("无参数提示用法", "用法" in t, t)
    t = asyncio.run(run_kick("/kick 3 [CQ:at,qq=1001] 99999999"))
    check("混合+去重+跳过", "已移出" in t and "不在群成员" in t, t)
    t = asyncio.run(run_kick("/kick 999999"))
    check("序号不存在按QQ号处理", "不在群成员" in t, t)


def test_gm_config_command():
    print("\n[14] 群管配置命令（/gm_config：查看/修改/持久化）")
    from app.group_manager.commands import _gm_config_handler

    tmp_cfg = os.path.join(tempfile.gettempdir(), "gm_config_test.yml")
    gm_config._config_path = tmp_cfg
    try:
        ok, msg = gm_config.set("inactive_kick_enabled", "true")
        check("set 布尔转换生效", ok and gm_config.get()["inactive_kick_enabled"] is True, msg)
        ok, msg = gm_config.set("inactive_kick_days", "14")
        check("set 整数转换生效", ok and gm_config.get()["inactive_kick_days"] == 14, msg)
        ok, msg = gm_config.set("welcome_msg", "第一行\\n第二行")
        check("set 文本 \\n 转真实换行", ok and gm_config.get()["welcome_msg"] == "第一行\n第二行", msg)
        ok, msg = gm_config.set("unknown_key", "1")
        check("未知配置项拒绝", not ok and "未知配置项" in msg, msg)
        ok, msg = gm_config.set("inactive_kick_days", "abc")
        check("非法整数拒绝", not ok, msg)
        ok, msg = gm_config.set("inactive_kick_enabled", "maybe")
        check("非法布尔拒绝", not ok, msg)

        text = gm_config.dump()
        check("dump 含键与描述", "inactive_kick_days" in text and "不活跃" in text, text[:40])

        # 持久化：重新加载可读到新值
        gm_config.reload_config()
        check("写回 yml 后 reload 生效", gm_config.get()["inactive_kick_days"] == 14)

        async def run(raw):
            return await _gm_config_handler(None, {"raw_message": raw, "group_id": "g1", "user_id": "u1"})

        judge, text = asyncio.run(run("/gm_config"))
        check("命令查看配置", judge and "群管配置" in text and "inactive_kick_enabled" in text, str(text)[:30])
        judge, text = asyncio.run(run("/gm_config set inactive_kick_enabled false"))
        check("命令修改配置", judge and "已设置" in text and gm_config.get()["inactive_kick_enabled"] is False, text)
        judge, text = asyncio.run(run("/gm_config set nope 1"))
        check("命令未知键拒绝", judge and "未知配置项" in text, text)
    finally:
        gm_config._config_path = gm_config.CONFIG_PATH
        gm_config._config = dict(gm_config.DEFAULTS)
        if os.path.exists(tmp_cfg):
            os.remove(tmp_cfg)


if __name__ == "__main__":
    test_config_defaults()
    test_member_join_flow()
    test_observation_kick()
    test_tier_state_machine()
    test_auto_approve()
    test_query_and_commands()
    test_event_bus_integration()
    test_backfill()
    test_auto_backfill_pending()
    test_members_list()
    test_never_kick_self()
    test_inactive_kick()
    test_inactive_list_and_kick()
    test_gm_config_command()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
