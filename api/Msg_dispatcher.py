import json

from api.Logger_owner import Logger

# 命令注册中心：各 app 的命令在模块导入时注册，统一分发/鉴权/帮助
from app.core.commands import registry
import app.core.commands.bootstrap  # 注册内建 /help
import app.Lssuing.commands         # 注册权限系统命令
import app.group_manager.commands   # 注册群管命令（含事件订阅）

# 启动审计：输出命令注册统计与冲突报告（同名/别名冲突、格式问题、前缀重叠）
registry.summary()


class Main_dispatcher_and_run:
    """
    插件功能器,功能接口,用于注册
    """
    def __init__(self):
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
