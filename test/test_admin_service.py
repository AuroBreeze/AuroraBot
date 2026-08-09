"""/admin 命令：管理系统管理员（set/add/del/list）测试"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.Lssuing.services.admin.admin_service import AdminService
from app.core.permission.service import PermissionService
from app.core.permission.store import PermissionStore

PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


def fresh_service():
    tmp = tempfile.mkdtemp(prefix="admin_test_")
    db_path = os.path.join(tmp, "test.db")
    store = PermissionStore(db_path)
    svc = PermissionService(store)
    return svc, store, tmp


def make_msg(raw, user="10001"):
    return {"raw_message": raw, "user_id": user, "group_id": "g1"}


async def run(handler, raw, user="10001"):
    return await handler(None, make_msg(raw, user))


def test_admin_command():
    print("\n[1] /admin 命令：set/add/del/list + 防锁死")
    svc, store, tmp = fresh_service()
    svc.store.seed_admin("10001")  # 初始管理员

    import app.Lssuing.services.admin.admin_service as admin_mod
    old_perm = admin_mod.permission_service
    admin_mod.permission_service = svc  # handler 内 is_admin 用测试实例

    svc_holder = AdminService()
    # monkeypatch 配置路径到临时文件，避免污染真实 config/_config.yml
    cfg_path = os.path.join(tmp, "_config.yml")
    svc_holder._update_config_admin = lambda qq: _write_cfg(cfg_path, qq)

    async def main():
        try:
            # 非管理员被拒
            ok, text = await run(svc_holder.admin_handler, "/admin list", user="99999")
            check("非管理员被拒", "仅系统管理员" in text, text)

            # list（1 人）
            ok, text = await run(svc_holder.admin_handler, "/admin list")
            check("list 显示管理员", "10001" in text and "1 人" in text, text)

            # set：写配置 + 立即生效
            ok, text = await run(svc_holder.admin_handler, "/admin set 20002")
            check("set 写配置提示", "QQbot_admin_account = 20002" in text, text)
            check("set 后立即生效", svc.is_admin("20002"), text)
            check("set 写入 yml 文件", "20002" in open(cfg_path, encoding="utf-8").read())

            # add
            ok, text = await run(svc_holder.admin_handler, "/admin add 30003")
            check("add 添加成功", "添加成功" in text and svc.is_admin("30003"), text)

            # del
            ok, text = await run(svc_holder.admin_handler, "/admin del 30003")
            check("del 移除成功", "已移除" in text and not svc.is_admin("30003"), text)

            # 防锁死：删到只剩 1 名（10001）后拒绝删除
            ok, text = await run(svc_holder.admin_handler, "/admin del 20002")
            check("del 到剩 1 名", "已移除" in text and not svc.is_admin("20002"), text)
            ok, text = await run(svc_holder.admin_handler, "/admin del 10001")
            check("删除最后一名被拒", "至少保留一名" in text and svc.is_admin("10001"), text)
            ok, text = await run(svc_holder.admin_handler, "/admin del 10001")
            check("重复删最后一名仍被拒", "至少保留一名" in text and svc.is_admin("10001"), text)

            # 非法输入
            ok, text = await run(svc_holder.admin_handler, "/admin set abc")
            check("非数字 QQ 拒绝", "纯数字" in text, text)
            ok, text = await run(svc_holder.admin_handler, "/admin foo")
            check("未知操作提示", "未知操作" in text, text)
        finally:
            admin_mod.permission_service = old_perm

    asyncio.run(main())


def _write_cfg(path, qq):
    import io
    import yaml
    cfg = {}
    cfg.setdefault("basic_settings", {})["QQbot_admin_account"] = str(qq)
    io.open(path, "w", encoding="utf-8", newline="").write(
        yaml.dump(cfg, allow_unicode=True, sort_keys=False)
    )
    return True, f"已写入配置 config/_config.yml：QQbot_admin_account = {qq}"


if __name__ == "__main__":
    test_admin_command()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
