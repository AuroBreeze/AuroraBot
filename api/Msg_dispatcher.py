import json
import asyncio

# 命令注册中心：各 app 的命令在模块导入时注册，统一分发/鉴权/帮助
from app.core.commands import registry
import app.core.commands.bootstrap  # 注册内建 /help
import app.Lssuing.commands         # 注册权限系统命令
import app.Timed_announcement.commands  # 注册定时喊话命令
from app.Timed_announcement.announcement_main import AnnouncementChecker

# 启动审计：输出命令注册统计与冲突报告（同名/别名冲突、格式问题、前缀重叠）
registry.summary()


class Main_dispatcher_and_run:
    """
    插件功能器,功能接口,用于注册
    """
    def __init__(self):
        self.msg_dispatcher = Msg_dispatcher()
        self.announcement_checker = None

    async def handle_event(self, websocket, message):  # 消息处理
        await self.msg_dispatcher.handle_event(websocket, message)

    async def start_background_tasks(self, websocket):
        """
        启动后台任务，包括定时喊话检查
        """
        if not self.announcement_checker:
            self.announcement_checker = AnnouncementChecker(websocket)
            asyncio.create_task(self._announcement_check_loop())

    async def _announcement_check_loop(self):
        """
        定时喊话检查循环
        """
        while True:
            try:
                if self.announcement_checker:
                    await self.announcement_checker.check_and_execute()
            except Exception as e:
                import traceback
                traceback.print_exc()
            # 每分钟检查一次
            await asyncio.sleep(60)


class Msg_dispatcher:
    """
    原始消息分发处理器：统一走命令注册中心
    """
    async def handle_event(self, websocket, message):  # 事件处理器(功能注册处)
        try:
            if isinstance(message, str):
                message = json.loads(message)
            # 统一命令分发：匹配、鉴权、执行、回复
            await registry.dispatch(websocket, message)
        except Exception as e:
            import traceback
            traceback.print_exc()
