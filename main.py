from api.ws_connect import Websocket_receiver
import asyncio


async def main():
    # 启动业务层热更新文件监控（修改 app 业务代码后自动重载，无需重启进程）
    from app.core.hot_reload import hot_reloader
    await hot_reloader.start_watch(interval=2.0)

    ws_receiver = Websocket_receiver()
    await ws_receiver.start_receiver()


if __name__ == '__main__':
    asyncio.run(main())
