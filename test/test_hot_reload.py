"""
业务层热更新回归测试（临时脚本，使用临时模块模拟 app 热更新，测试结束清理）

运行: uv run python test/test_hot_reload.py
"""
import asyncio
import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

# 确保从项目根可导入 app.*（脚本位于 test/ 子目录）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.core.hot_reload as hr_mod
from app.core.commands import registry

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


APP_NAME = "热更新测试"
MOD_NAME = "hot_test_app"


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        import json
        self.sent.append(json.loads(data))


def write_module(tmpdir, version):
    """写入指定版本的测试模块（注册 /hot_test 命令，handler 返回 hot-{version}）"""
    path = os.path.join(tmpdir, MOD_NAME + ".py")
    Path(path).write_text(
        f'from app.core.commands import registry as _r\n'
        f'from app.core.commands.model import Command\n'
        f'async def _handler(ws, m):\n'
        f'    return True, "hot-{version}"\n'
        f'_r.register(Command(name="/hot_test", handler=_handler, '
        f'description="hot", required_level=4, app_name="{APP_NAME}"))\n',
        encoding="utf-8",
    )
    return path


async def dispatch_once(raw):
    ws = FakeWS()
    handled = await registry.dispatch(ws, {"raw_message": raw, "group_id": "g", "user_id": "u"})
    text = ""
    if ws.sent:
        text = ws.sent[0]["params"]["message"][0]["data"]["text"]
    return handled, text


def test_unregister():
    print("\n[1] registry unregister / unregister_by_app")
    from app.core.commands.registry import CommandRegistry
    from app.core.commands.model import Command

    async def h(ws, m):
        return True, "ok"

    r = CommandRegistry()
    r.register(Command(name="/a", handler=h, app_name="X", aliases=["aa"]))
    r.register(Command(name="/b", handler=h, app_name="Y"))
    r.register(Command(name="/c", handler=h, app_name="X"))

    check("unregister 单条", r.unregister("/a") and r.match("/a") is None and r.match("aa") is None)
    check("unregister 不存在返回 False", not r.unregister("/nope"))
    removed = r.unregister_by_app("X")
    check("unregister_by_app 移除该 app 全部", sorted(removed) == ["/c"], str(removed))
    check("别名一并清理", r.match("/c") is None)
    check("其他 app 不受影响", r.match("/b") is not None)


def test_reload_lifecycle():
    print("\n[2] 热更新生命周期：v1 → v2 → 新命令生效")
    tmpdir = tempfile.mkdtemp(prefix="hot_test_")
    sys.path.insert(0, tmpdir)
    old_root = hr_mod._SRC_ROOT
    hr_mod._SRC_ROOT = tmpdir
    hr = hr_mod.HotReloader()

    try:
        # v1 模块
        write_module(tmpdir, "v1")
        mod = importlib.import_module(MOD_NAME)
        hr.register_app(APP_NAME, [MOD_NAME])

        handled, text = asyncio.run(dispatch_once("/hot_test"))
        check("v1 命令可执行", handled and text == "hot-v1", text)

        # 未变更时 check_changes 为空
        check("无变更不触发", hr.check_changes() == [])

        # 改为 v2（模拟修改源码）
        write_module(tmpdir, "v2")
        check("变更被检测", hr.check_changes() == [APP_NAME], str(hr.check_changes()))

        result = hr.reload_app(APP_NAME)
        check("重载成功", "重载成功" in result, result)
        handled, text = asyncio.run(dispatch_once("/hot_test"))
        check("v2 新命令生效", handled and text == "hot-v2", text)
        check("v2 handler 是重载后的模块", registry.match("/hot_test").handler.__module__ == MOD_NAME,
              str(registry.match("/hot_test").handler))

        # 二次重载后无残留旧模块状态
        write_module(tmpdir, "v2")
        hr.reload_app(APP_NAME)
        handled, text = asyncio.run(dispatch_once("/hot_test"))
        check("重复重载正常", text == "hot-v2", text)
    finally:
        registry.unregister_by_app(APP_NAME)
        hr_mod._SRC_ROOT = old_root
        sys.modules.pop(MOD_NAME, None)
        sys.path.remove(tmpdir)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_syntax_error_abort():
    print("\n[3] 语法错误保护：不重载，旧命令保留")
    tmpdir = tempfile.mkdtemp(prefix="hot_bad_")
    sys.path.insert(0, tmpdir)
    old_root = hr_mod._SRC_ROOT
    hr_mod._SRC_ROOT = tmpdir
    hr = hr_mod.HotReloader()

    try:
        write_module(tmpdir, "v1")
        importlib.import_module(MOD_NAME)
        hr.register_app(APP_NAME, [MOD_NAME])

        # 写入语法错误版本
        Path(os.path.join(tmpdir, MOD_NAME + ".py")).write_text(
            "def broken(:\n    pass\n", encoding="utf-8"
        )
        result = hr.reload_app(APP_NAME)
        check("语法错误中止重载", "语法错误" in result, result)
        handled, text = asyncio.run(dispatch_once("/hot_test"))
        check("旧命令仍可用", text == "hot-v1", text)
    finally:
        registry.unregister_by_app(APP_NAME)
        hr_mod._SRC_ROOT = old_root
        sys.modules.pop(MOD_NAME, None)
        sys.path.remove(tmpdir)
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_unregister()
    test_reload_lifecycle()
    test_syntax_error_abort()
    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    sys.exit(1 if FAIL else 0)
