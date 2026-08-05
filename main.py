from api.ws_connect import Websocket_receiver
import asyncio


async def main():
    # ---- 装配层：注册各 app 命令（模块导入即注册），输出启动审计 ----
    import app.core.commands.bootstrap   # 注册内建 /help
    import app.Lssuing.commands          # 注册权限系统命令
    import app.group_manager.commands    # 注册群管命令（含事件订阅）
    from app.core.commands import registry
    registry.summary()

    # 启动业务层热更新文件监控（修改 app 业务代码后自动重载，无需重启进程）
    from app.core.hot_reload import hot_reloader
    await hot_reloader.start_watch(interval=2.0)

    from app.core.tasks import task_scheduler
    from app.group_manager import config as gm_config

    # 后台周期任务始终注册（开关由 service 方法内部自检，/gm_config set 后动态生效）；
    # 包装函数延迟取最新单例，避免热更新重载后任务绑定旧实例/旧配置
    async def _auto_backfill_latest():
        from app.group_manager.service import group_manager_service
        await group_manager_service.auto_backfill_pending()

    async def _scan_inactive_latest():
        from app.group_manager.service import group_manager_service
        await group_manager_service.scan_inactive_members()

    task_scheduler.periodic(
        "gm_auto_backfill",
        gm_config.get_int("auto_backfill_interval", 300),
        _auto_backfill_latest,
    )
    task_scheduler.periodic(
        "gm_inactive_kick",
        gm_config.get_int("inactive_kick_interval", 3600),
        _scan_inactive_latest,
    )

    ws_receiver = Websocket_receiver()
    await ws_receiver.start_receiver()


if __name__ == '__main__':
    asyncio.run(main())
