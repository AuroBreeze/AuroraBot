import json
import websockets
from api.Logger_owner import Logger # 美化日志输出
from api.Share_date import Raw_data # 导入原始数据队列（兼容保留）
import asyncio
from api.Botapi import QQAPI_list
from api.Msg_dispatcher import Main_dispatcher_and_run
from app.core.events import event_bus, EventType
from config.env import WS_URL

class Websocket_receiver:
    def __init__(self):
        self.logger = Logger("Websocket_receiver")  # 实例化日志类
        self.url = WS_URL  # 使用Docker服务名称代替localhost
        self.dispatcher = Main_dispatcher_and_run()
        self.api = None  # 连接建立后创建（统一 API 客户端）
        self._msg_handler = None  # MESSAGE 事件订阅者（随连接重建）

    def _route_message(self, data: dict):
        """
        消息路由：
        - 带 echo 的 OneBot API 响应 → 投递给等待中的 _call（echo 匹配）
        - 其他 → 事件总线（MESSAGE / GROUP_REQUEST / notice 等，按类型分发）
        返回是否路由为 API 响应。
        """
        echo = data.get("echo")
        if echo is not None and self.api is not None and echo in self.api._pending:
            self.api.dispatch_response(echo, data)
            return True
        return False

    async def msg_raw_receiver(self):
        self.logger.info("Starting Websocket Receiver")
        self.logger.info("Websocket URL: %s"% self.url)

        try:
            async with websockets.connect(self.url) as websocket:
                self.logger.info("Websocket Connected: %s" % "QQbot_server_started")

                # 统一 API 客户端：响应通过 echo 匹配回流（由 _route_message 投递）
                self.api = QQAPI_list(websocket)
                from app.core.runtime import set_api
                set_api(self.api)  # 注入运行时上下文（事件订阅者使用）

                # MESSAGE 事件订阅者（闭包捕获当前连接）；重连时先退订旧的
                if self._msg_handler is not None:
                    event_bus.unsubscribe(EventType.MESSAGE, self._msg_handler)

                async def _on_message(event):
                    # 消息 → 命令注册中心统一分发（匹配/鉴权/执行/回复）
                    await self.dispatcher.handle_event(websocket, event.data)

                self._msg_handler = _on_message
                event_bus.subscribe(EventType.MESSAGE, self._msg_handler)

                async for message in websocket:
                    self.logger.info("Message Received: %s" % message)
                    await Raw_data.put(message)  # 兼容保留
                    try:
                        data = json.loads(message)
                    except (json.JSONDecodeError, TypeError):
                        self.logger.error(f"无法解析的 WS 消息: {message}")
                        continue
                    # 记录 bot 自身 QQ（业务层用于避免误踢自己等）
                    if data.get("self_id"):
                        from app.core.runtime import set_self_id
                        set_self_id(data["self_id"])
                    if not self._route_message(data):
                        # 事件处理后台化：读取循环必须保持快速 recv，
                        # 否则事件处理中调 API 等响应会与 recv 自锁（响应永远读不到）
                        asyncio.create_task(event_bus.emit_raw(data))

        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.error("Websocket Connection Closed Error: %s" % e)
        except Exception as e:
            self.logger.error("Websocket Receiver Error: %s" % e)
        except:
            self.logger.error("Websocket Receiver Error: %s" % "Unknown Error or closed()")
        finally:
            from app.core.runtime import set_api
            set_api(None)  # 断开连接，清空运行时上下文

    async def start_receiver(self):
        await self.msg_raw_receiver()
if __name__ == '__main__':
    asyncio.run(Websocket_receiver().start_receiver())
