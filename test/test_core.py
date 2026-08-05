"""
TaskScheduler + MemberStore 基础设施测试

运行: uv run python test/test_core.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.tasks import TaskScheduler
from app.core.member_store import MemberStore

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


def test_scheduler_schedule():
    print("\n[1] TaskScheduler.schedule 延时执行")

    async def scenario():
        s = TaskScheduler()
        ran = []

        async def fn():
            ran.append("once")

        s.schedule("t1", 0.05, fn)
        await asyncio.sleep(0.15)
        return s, ran

    s, ran = asyncio.run(scenario())
    check("任务注册并执行", ran == ["once"], str(ran))
    check("执行后清理", "t1" not in s.active())


def test_scheduler_periodic_and_cancel():
    print("\n[2] TaskScheduler.periodic + cancel + 同名覆盖")

    async def scenario():
        s = TaskScheduler()
        count = []

        async def fn():
            count.append(1)

        s.periodic("p1", 0.03, fn)
        await asyncio.sleep(0.1)
        n1 = len(count)
        s.cancel("p1")
        await asyncio.sleep(0.06)
        n2 = len(count)

        # 同名覆盖
        s.periodic("dup", 0.02, fn)
        s.periodic("dup", 0.02, fn)
        dup_count = s.active().count("dup")
        s.cancel("dup")
        return n1, n2, s, dup_count

    n1, n2, s, dup_count = asyncio.run(scenario())
    check("周期任务多次执行", n1 >= 2, str(n1))
    check("cancel 后停止", n2 == n1, str((n2, n1)))
    check("取消后移出活跃", "p1" not in s.active())
    check("同名任务不重复", dup_count == 1, str(dup_count))


def test_scheduler_exception_isolation():
    print("\n[3] 任务异常隔离")

    async def scenario():
        s = TaskScheduler()

        async def bad():
            raise RuntimeError("task boom")

        async def good():
            pass

        s.schedule("bad", 0.02, bad)
        s.schedule("good", 0.02, good)
        await asyncio.sleep(0.1)
        return s

    s = asyncio.run(scenario())
    check("异常任务不影响其他任务", "bad" not in s.active() and "good" not in s.active())


def test_member_store_crud():
    print("\n[4] MemberStore 基础读写")
    tmp = tempfile.mkdtemp(prefix="member_test_")
    store = MemberStore(os.path.join(tmp, "m.db"))

    store.record_join("g1", "u1", join_time="2026-01-01 10:00:00")
    store.record_message("g1", "u1")
    m = store.get_member("g1", "u1")
    check("入群记录", m is not None and m["join_time"] == "2026-01-01 10:00:00", str(m))
    check("最后发言已更新", m["last_active"] is not None, str(m))

    check("不存在成员返回 None", store.get_member("g1", "nobody") is None)

    store.record_join("g1", "u2", join_time="2026-01-02 10:00:00")
    store.record_leave("g1", "u1")
    check("退群清理", store.get_member("g1", "u1") is None)
    check("其他成员保留", store.get_member("g1", "u2") is not None)

    members = store.get_members("g1")
    check("成员列表", [m["user_id"] for m in members] == ["u2"], str(members))


def test_member_store_extras():
    print("\n[5] MemberStore 扩展字段（业务状态机用）")
    tmp = tempfile.mkdtemp(prefix="member_extra_")
    store = MemberStore(os.path.join(tmp, "m.db"))

    store.record_join("g1", "u1")
    check("默认 extras 为空", store.get_extras("g1", "u1") == {})
    store.set_extras("g1", "u1", {"tier": "钻石", "flow": "awaiting_reply"})
    check("set/get extras", store.get_extras("g1", "u1") == {"tier": "钻石", "flow": "awaiting_reply"})
    store.set_extras("g1", "u1", {"tier": "王者"})
    check("extras 整体替换", store.get_extras("g1", "u1") == {"tier": "王者"})


if __name__ == "__main__":
    test_scheduler_schedule()
    test_scheduler_periodic_and_cancel()
    test_scheduler_exception_isolation()
    test_member_store_crud()
    test_member_store_extras()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
