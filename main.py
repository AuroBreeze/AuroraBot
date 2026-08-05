from api.ws_connect import Websocket_receiver
import asyncio


async def main():
    # 启动业务层热更新文件监控（修改 app 业务代码后自动重载，无需重启进程）
    from app.core.hot_reload import hot_reloader
    await hot_reloader.start_watch(interval=2.0)

    # 自动补记录：未处理过的群自动补一次（幂等，周期检查；API 未连接时静默跳过）
    from app.core.tasks import task_scheduler
    from app.group_manager import config as gm_config
    from app.group_manager.service import group_manager_service
    if gm_config.get_bool("auto_backfill", True):
        interval = gm_config.get_int("auto_backfill_interval", 300)
        task_scheduler.periodic(
            "gm_auto_backfill", interval,
            group_manager_service.auto_backfill_pending,
        )

    ws_receiver = Websocket_receiver()
    await ws_receiver.start_receiver()


if __name__ == '__main__':
    asyncio.run(main())
