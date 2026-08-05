import json

from api.Logger_owner import Logger

from app.core.commands import registry


class Main_dispatcher_and_run:
    """
    插件功能器,功能接口,用于注册

    各 app 的命令注册/事件订阅/启动审计由 main.py（装配层）负责，
    本类仅做消息分发：统一走命令注册中心。
    """
    def __init__(self):
        self.logger = Logger("Main_dispatcher_and_run")
        self.msg_dispatcher = Msg_dispatcher()

    async def handle_event(self, websocket, message):  # 消息处理
        await self.msg_dispatcher.handle_event(websocket, message)


class Msg_dispatcher:
    """
    原始消息分发处理器：统一走命令注册中心
    """
    def __init__(self):
        self.logger = Logger("Msg_dispatcher")

    async def handle_event(self, websocket, message):  # 事件处理器(功能注册处)
        try:
            if isinstance(message, str):
                message = json.loads(message)
            # 统一命令分发：匹配、鉴权、执行、回复
            await registry.dispatch(websocket, message)
        except Exception as e:
            self.logger.error(f"消息分发异常: {e}", exc_info=True)
