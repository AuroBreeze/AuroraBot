"""
权限底座核心逻辑回归测试（临时脚本，独立数据库，不污染生产数据）

运行: uv run python test_permission_core.py
"""
import asyncio
import os
import sys
import tempfile

from app.permission.constants import LEVEL_OWNER, LEVEL_ADMIN
from app.permission.store import PermissionStore
from app.permission.service import PermissionService

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")

def fresh_service():
    """构造独立数据库的服务实例"""
    tmp = tempfile.mkdtemp(prefix="perm_test_")
    db_path = os.path.join(tmp, "test.db")
    store = PermissionStore(db_path)
    svc = PermissionService(store)
    return svc, store

ADMIN = "10001"
OWNER = "20001"
USER_A = "30001"
USER_B = "30002"
GROUP_1 = "7770001"
GROUP_2 = "7770002"


def test_admin_seed():
    print("\n[1] 多管理员播种与判定")
    svc, store = fresh_service()
    check("非管理员默认 false", not svc.is_admin(OWNER))
    store.seed_admin(ADMIN)
    check("播种后 is_admin true", svc.is_admin(ADMIN))
    admins, err = svc.list_admins(ADMIN)
    check("admins 列表含 ADMIN", ADMIN in admins, err)
    svc.add_admin(ADMIN, OWNER, "手动添加")
    check("add_admin 生效", svc.is_admin(OWNER))
    svc.remove_admin(ADMIN, OWNER)
    check("remove_admin 生效", not svc.is_admin(OWNER))


def test_subscribe_and_group_auth():
    print("\n[2] 群组授权（subscribe）与群授权检查")
    svc, store = fresh_service()
    store.seed_admin(ADMIN)

    judge, msg = svc.subscribe_group(ADMIN, GROUP_1, OWNER, "now", 30, "all")
    check("管理员 subscribe 成功", judge, msg)
    check("群在授权期内", svc.check_group_authorized(GROUP_1))
    check("owner 获得 2 级", svc.check_user_permission(GROUP_1, OWNER, LEVEL_OWNER))

    judge, msg = svc.subscribe_group(OWNER, GROUP_2, "888", "now", 30, "all")
    check("非管理员 subscribe 被拒", not judge, msg)

    # 管理员登记 GROUP_2 后覆盖写入过期时间段（验证过期判定与外键保护）
    judge, msg = svc.subscribe_group(ADMIN, GROUP_2, "888", "now", 30, "all")
    check("管理员 subscribe GROUP_2 成功", judge, msg)
    store.add_group_authorization(GROUP_2, "888", "2020-01-01 00:00:00", "2020-01-02 00:00:00", "all")
    check("过期群授权检查为 false", not svc.check_group_authorized(GROUP_2))


def test_raise_privilege_guard():
    print("\n[3] 提权防护（防覆盖降级/防同级篡改）")
    svc, store = fresh_service()
    store.seed_admin(ADMIN)
    svc.subscribe_group(ADMIN, GROUP_1, OWNER, "now", 30, "all")

    # 2 级 owner 正常提权普通用户
    judge, msg = svc.add_user_permission(OWNER, GROUP_1, USER_A, LEVEL_ADMIN)
    check("owner 提权 USER_A 为 3 级成功", judge, msg)
    check("USER_A 有 3 级", svc.check_user_permission(GROUP_1, USER_A, LEVEL_ADMIN))

    # 2 级 owner 试图覆盖已有 3 级用户（重复提权/篡改 parent）→ 拒绝
    judge, msg = svc.add_user_permission(OWNER, GROUP_1, USER_A, LEVEL_ADMIN)
    check("重复提权同级被拒", not judge, msg)

    # 2 级 owner 提权 USER_B 后，再试图把另一个 2 级（管理员 admin 已订阅群主？）——
    # 构造：把 OWNER 之外的另一个 2 级：管理员 admin 跨群提权 B 为 2 级
    judge, msg = svc.admin_raise_user(ADMIN, GROUP_1, USER_B, LEVEL_OWNER)
    check("管理员可跨群提权 USER_B 为 2 级", judge, msg)
    # 2 级 OWNER 试图覆盖 2 级 USER_B（降级篡改）→ 拒绝
    judge, msg = svc.add_user_permission(OWNER, GROUP_1, USER_B, LEVEL_ADMIN)
    check("2级无法覆盖同级 2 级", not judge, msg)
    # 管理员可以管理/覆盖任意级别
    judge, msg = svc.add_user_permission(ADMIN, GROUP_1, USER_B, LEVEL_ADMIN)
    check("管理员可修改任意级别用户", judge, msg)

    # 3 级用户不能提权
    judge, msg = svc.add_user_permission(USER_A, GROUP_1, "40001", LEVEL_ADMIN)
    check("3级用户不能提权", not judge, msg)


def test_list_group_users_scope():
    print("\n[4] list_user 归属校验（防跨群枚举）")
    svc, store = fresh_service()
    store.seed_admin(ADMIN)
    svc.subscribe_group(ADMIN, GROUP_1, OWNER, "now", 30, "all")
    svc.subscribe_group(ADMIN, GROUP_2, "888", "now", 30, "all")
    svc.add_user_permission(OWNER, GROUP_1, USER_A, LEVEL_ADMIN)

    # GROUP_1 的成员 USER_A 查看 GROUP_1 自己 → 允许
    rows, err = svc.list_group_users(USER_A, GROUP_1)
    check("本群用户可查看本群列表", not err and any(r[0] == USER_A for r in rows), err)
    # GROUP_1 的成员 USER_A 查看 GROUP_2 → 拒绝（跨群枚举）
    rows, err = svc.list_group_users(USER_A, GROUP_2)
    check("跨群查看被拒", rows == [] and "不属于" in (err or ""), err)
    # 管理员可查看任意群
    rows, err = svc.list_group_users(ADMIN, GROUP_2)
    check("管理员可查看任意群", not err, err)


def test_kick_and_unsubscribe():
    print("\n[5] kick / unsubscribe 与级联删除")
    svc, store = fresh_service()
    store.seed_admin(ADMIN)
    svc.subscribe_group(ADMIN, GROUP_1, OWNER, "now", 30, "all")
    svc.add_user_permission(OWNER, GROUP_1, USER_A, LEVEL_ADMIN)

    judge, msg = svc.kick_group(ADMIN, GROUP_1)
    check("kick 语法正确且成功", judge, msg)
    groups, err = svc.list_groups(ADMIN)
    check("kick 后群列表为空", groups == [], err)
    # 群授权级联失效
    check("kick 后群授权检查为 false", not svc.check_group_authorized(GROUP_1))

    judge, msg = svc.unsubscribe_group(ADMIN, GROUP_2)
    check("unsubscribe 不存在的群返回失败", not judge)


def test_admin_raise_cross_group():
    print("\n[6] 管理员跨群提权（无需在目标群有记录）")
    svc, store = fresh_service()
    store.seed_admin(ADMIN)
    svc.subscribe_group(ADMIN, GROUP_1, OWNER, "now", 30, "all")
    # ADMIN 不在 GROUP_1 的 user_permissions 表中，仍可跨群提权（修复旧版 bug）
    judge, msg = svc.admin_raise_user(ADMIN, GROUP_1, USER_B, LEVEL_ADMIN)
    check("管理员跨群提权成功", judge, msg)
    check("USER_B 获得 3 级", svc.check_user_permission(GROUP_1, USER_B, LEVEL_ADMIN))


def test_simple_subscribe_command():
    print("\n[7] 简单版群授权命令 /sub_group（含群主自动授权）")
    from app.Lssuing.services.admin.group_service import GroupService
    import app.Lssuing.services.admin.group_service as group_svc_mod

    tmp = tempfile.mkdtemp(prefix="perm_test_sub_")
    svc = PermissionService(PermissionStore(os.path.join(tmp, "t.db")))
    svc.store.seed_admin(ADMIN)

    # 模拟 OneBot 群成员查询：群 7770001/7770002 的群主为 20001
    class FakeQQAPI:
        def __init__(self, ws):
            pass

        async def get_group_member_list(self, group_id):
            return [
                {"user_id": "20001", "role": "owner"},
                {"user_id": "30001", "role": "member"},
            ]

    old_perm = group_svc_mod.permission_service
    old_api = group_svc_mod.QQAPI_list
    group_svc_mod.permission_service = svc
    group_svc_mod.QQAPI_list = FakeQQAPI
    try:
        g = GroupService()
        FAKE_WS = object()

        async def run(raw, uid=ADMIN):
            return await g.authorize_group_simple(FAKE_WS, {"raw_message": raw, "user_id": uid})

        # 基本：/sub_group <群号> <天数>，获权用户默认执行者
        judge, msg = asyncio.run(run("/sub_group 7770001 30"))
        check("简单版订阅成功", judge, msg)
        check("群在授权期内", svc.check_group_authorized("7770001"))
        check("获权用户默认为执行者(2级)", svc.check_user_permission("7770001", ADMIN, LEVEL_OWNER))
        check("真实群主自动获得 2 级", svc.check_user_permission("7770001", "20001", LEVEL_OWNER))

        # 显式获权用户 = 群主本人：不重复授权，群主为 2 级
        judge, msg = asyncio.run(run("/sub_group 7770002 30 20001"))
        check("显式获权用户生效", judge and svc.check_user_permission("7770002", "20001", LEVEL_OWNER), msg)

        # 别名 sub_group
        judge, msg = asyncio.run(run("sub_group 7770003 7"))
        check("别名 sub_group 可用", judge, msg)

        # 参数错误
        judge, msg = asyncio.run(run("/sub_group 7770004 abc"))
        check("天数非整数被拒", not judge and "整数" in msg, msg)
        judge, msg = asyncio.run(run("/sub_group 7770005"))
        check("缺少参数被拒", not judge and "格式" in msg, msg)
        judge, msg = asyncio.run(run("/sub_group 7770006 -1"))
        check("负数天数被拒", not judge and "负数" in msg, msg)

        # 非管理员被拒
        judge, msg = asyncio.run(run("/sub_group 7770007 30", uid=OWNER))
        check("非管理员订阅被拒", not judge, msg)

        # 群主查询失败（API 异常）不阻断主流程
        class BoomAPI(FakeQQAPI):
            async def get_group_member_list(self, group_id):
                raise RuntimeError("api down")

        group_svc_mod.QQAPI_list = BoomAPI
        judge, msg = asyncio.run(run("/sub_group 7770008 30"))
        check("群主查询失败不影响订阅", judge, msg)
    finally:
        group_svc_mod.permission_service = old_perm
        group_svc_mod.QQAPI_list = old_api


if __name__ == "__main__":
    test_admin_seed()
    test_subscribe_and_group_auth()
    test_raise_privilege_guard()
    test_list_group_users_scope()
    test_kick_and_unsubscribe()
    test_admin_raise_cross_group()
    test_simple_subscribe_command()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
