"""
任务调度器（app/core/tasks.py）

基于 asyncio 的延时/周期任务管理：
- schedule(name, delay, fn): 延时执行一次（如"入群 10 分钟未发言检查"的倒计时）
- periodic(name, interval, fn): 周期执行（如活跃统计）
- 同名任务覆盖前自动取消旧的；任务异常隔离（记录日志不中断其他任务）
"""
import asyncio
from typing import Awaitable, Callable, Optional

from api.Logger_owner import Logger

# 任务函数签名: async fn(*args) -> None
TaskFn = Callable[..., Awaitable[None]]


class TaskScheduler:
    """延时/周期任务调度（进程内单例）"""

    def __init__(self):
        self.logger = Logger("task_scheduler")
        self._tasks: dict[str, asyncio.Task] = {}

    def _cleanup(self, name: str):
        self._tasks.pop(name, None)

    def cancel(self, name: str) -> bool:
        """取消任务；不存在返回 False"""
        task = self._tasks.get(name)
        if task is None:
            return False
        task.cancel()
        self._tasks.pop(name, None)
        self.logger.info(f"任务已取消: {name}")
        return True

    def active(self) -> list[str]:
        """当前活跃任务名列表"""
        return list(self._tasks.keys())

    def schedule(self, name: str, delay: float, fn: TaskFn, *args) -> str:
        """
        delay 秒后执行一次 fn(*args)。
        同名任务自动覆盖（先取消旧任务）。
        """
        if name in self._tasks:
            self.cancel(name)

        async def _run():
            try:
                await asyncio.sleep(delay)
                await fn(*args)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.logger.error(f"任务 [{name}] 执行异常: {e}")
            finally:
                self._cleanup(name)

        self._tasks[name] = asyncio.create_task(_run(), name=name)
        self.logger.debug(f"已调度任务 [{name}] 延时 {delay}s")
        return name

    def periodic(self, name: str, interval: float, fn: TaskFn, *args) -> str:
        """
        每 interval 秒执行一次 fn(*args)，直到 cancel(name) 取消。
        同名任务自动覆盖。
        """
        if name in self._tasks:
            self.cancel(name)

        async def _run():
            try:
                while True:
                    await asyncio.sleep(interval)
                    try:
                        await fn(*args)
                    except Exception as e:
                        self.logger.error(f"周期任务 [{name}] 执行异常: {e}")
            except asyncio.CancelledError:
                pass
            finally:
                self._cleanup(name)

        self._tasks[name] = asyncio.create_task(_run(), name=name)
        self.logger.debug(f"已启动周期任务 [{name}] 间隔 {interval}s")
        return name


# 全局单例
task_scheduler = TaskScheduler()
