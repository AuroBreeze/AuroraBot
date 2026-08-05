"""
业务层热更新（app/core/hot_reload.py）

目标：修改 app 业务代码（services / commands）后无需重启进程即生效。

范围边界：
- ✅ 热更新：已注册 app 的业务模块（如 app.Lssuing 的 services + commands）
- ❌ 不重载：核心层（app/core/commands、app/permission）、连接层（api/、main.py）
  —— 保证注册中心/权限门面/数据库连接稳定；改动这些仍需重启

原理：
1. 声明式注册：app 声明自己的模块清单（依赖在前），HotReloader 记录其文件 mtime
2. 文件监控：asyncio 轮询 mtime 变化（自动触发）
3. 重载流程：py_compile 语法预检 → registry.unregister_by_app（移除旧命令）
   → importlib.reload 全部模块（commands 模块重载时自动重新注册新命令）
   → 输出审计报告
4. 失败保护：语法错误不重载（避免把 bot 搞挂）；运行时错误记录严重日志
"""
import asyncio
import importlib
import os
import py_compile
from typing import Callable, Optional

from api.Logger_owner import Logger
from .commands import registry

# 项目源码根目录（app 包所在）
_SRC_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class HotReloader:
    """业务层热更新管理器（进程内单例）"""

    def __init__(self):
        self.logger = Logger("hot_reload")
        # app 显示名 -> 模块清单（依赖在前，commands 模块放最后）
        self._apps: dict[str, list[str]] = {}
        # 模块名 -> 最近一次 mtime
        self._mtime: dict[str, float] = {}
        self._task: Optional[asyncio.Task] = None
        self._reloading: set[str] = set()  # 防止同一 app 并发重载

    # ---------- 声明 ----------

    def register_app(self, app_name: str, modules: list[str]) -> None:
        """声明可热更新的 app：app_name 与 registry 注册命令时的 app_name 一致"""
        self._apps[app_name] = list(modules)
        for mod in modules:
            self._mtime.setdefault(mod, self._file_mtime(mod))
        self.logger.info(f"热更新已登记 app [{app_name}]: {len(modules)} 个模块")

    @staticmethod
    def _module_to_path(module: str) -> str:
        return os.path.join(_SRC_ROOT, *module.split(".")) + ".py"

    def _file_mtime(self, module: str) -> float:
        path = self._module_to_path(module)
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    # ---------- 检测 ----------

    def check_changes(self) -> list[str]:
        """返回有文件变更的 app 名列表"""
        changed = []
        for app_name, modules in self._apps.items():
            for mod in modules:
                if self._file_mtime(mod) != self._mtime.get(mod):
                    changed.append(app_name)
                    break
        return changed

    # ---------- 重载 ----------

    def reload_app(self, app_name: str) -> str:
        """重载指定 app，返回结果描述。失败时旧命令可能已被移除（记录严重日志）。"""
        if app_name not in self._apps:
            return f"app [{app_name}] 未登记热更新，无法重载"
        if app_name in self._reloading:
            return f"app [{app_name}] 正在重载中，跳过"

        self._reloading.add(app_name)
        try:
            modules = self._apps[app_name]
            report = []

            # 1. 语法预检：任一模块语法错误则整体中止（保留旧命令）
            bad = []
            for mod in modules:
                try:
                    py_compile.compile(self._module_to_path(mod), doraise=True)
                except py_compile.PyCompileError as e:
                    bad.append(f"{mod}: {e}")
            if bad:
                self.logger.error(f"app [{app_name}] 语法检查失败，中止重载:\n" + "\n".join(bad))
                return f"❌ app [{app_name}] 语法错误，未重载:\n" + "\n".join(bad)

            # 2. 快照旧命令 → 移除旧命令（含别名）→ 按依赖序重载
            snapshot = registry.snapshot(app_name)
            removed = registry.unregister_by_app(app_name)
            report.append(f"移除旧命令 {len(removed)} 条")

            # 3. 按依赖序重载模块（commands 模块重载时自动重新注册）
            for mod in modules:
                importlib.reload(importlib.import_module(mod))
                self._mtime[mod] = self._file_mtime(mod)

            # 4. 审计确认
            self.logger.info(f"app [{app_name}] 重载完成: {report[0]}")
            registry.summary()
            return f"✅ app [{app_name}] 重载成功（{report[0]}，新命令已注册）"
        except Exception as e:
            # 事务式回滚：重载失败时恢复旧命令，避免命令丢失
            snapshot = locals().get("snapshot", [])
            self.logger.error(f"app [{app_name}] 重载失败，回滚旧命令: {e}")
            registry.restore(app_name, snapshot)
            registry.summary()
            return f"❌ app [{app_name}] 重载失败已回滚: {e}（旧命令已恢复，请检查日志）"
        finally:
            self._reloading.discard(app_name)

    # ---------- 监控 ----------

    async def watch(self, interval: float = 2.0, callback: Optional[Callable[[str], None]] = None):
        """轮询文件变更并自动重载（后台任务）。callback 可选：重载后回调。"""
        self.logger.info(f"热更新文件监控已启动（轮询间隔 {interval}s）")
        while True:
            try:
                for app_name in self.check_changes():
                    self.logger.info(f"检测到 app [{app_name}] 文件变更，自动重载")
                    result = self.reload_app(app_name)
                    self.logger.info(result)
                    if callback:
                        callback(result)
            except Exception as e:
                self.logger.error(f"热更新监控异常: {e}")
            await asyncio.sleep(interval)

    async def start_watch(self, interval: float = 2.0, callback=None) -> bool:
        """启动监控任务（幂等）"""
        if self._task is not None and not self._task.done():
            return False
        self._task = asyncio.create_task(self.watch(interval, callback))
        return True


# 全局单例
hot_reloader = HotReloader()
