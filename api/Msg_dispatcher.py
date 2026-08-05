import json
import asyncio
from app.Lssuing.mandated import Mandated
# from app.Learn_clock.clock_main import Clock_learn
# from app.Commodity_lssuing.manage import Manage
# from app.Proxy_talk.proxy_main import Proxy_talk
from app.Timed_announcement.announcement_main import TimedAnnouncement, AnnouncementChecker


class Main_dispatcher_and_run:
    """
    插件功能器,功能接口,用于注册
    """
    def __init__(self):
        self.msg_dispatcher = Msg_dispatcher()
        self.announcement_checker = None
        
    async def handle_event(self, websocket, message): # 消息处理
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
    原始消息分发处理器
    """
    async def handle_event(self, websocket, message): # 事件处理器(功能注册处)
        # await self.Learn_clock(websocket, message)
        await self.Lssuing(websocket, message)
        await self.Timed_announcement(websocket, message)
        # await self.Commodity_lssuing(websocket, message)
        # await self.Proxy_talk(websocket, message)
        
    # async def Learn_clock(self, websocket, message):
    #     try:
    #         if isinstance(message, str):
    #             message = json.loads(message)
    #         await Clock_learn(websocket, message).handle_clock()
    #     except Exception as e:
    #         import traceback
    #         traceback.print_exc()
        
    async def Lssuing(self, websocket, message):
        try:
            if isinstance(message, str):
                message = json.loads(message)
            await Mandated(websocket, message).handle_event()
        except Exception as e:
            import traceback
            traceback.print_exc()
            
    async def Timed_announcement(self, websocket, message):
        try:
            if isinstance(message, str):
                message = json.loads(message)
            await TimedAnnouncement(websocket, message).handle_event()
        except Exception as e:
            import traceback
            traceback.print_exc()
            
    # async def Commodity_lssuing(self, websocket, message):
    #     try:
    #         if isinstance(message, str):
    #             message = json.loads(message)
    #         from app.Commodity_lssuing.manage import Manage  # 延迟导入（依赖 matplotlib/pandas/numpy extra）
    #         await Manage(websocket, message).handle_event()
    #     except Exception as e:
    #         import traceback
    #         traceback.print_exc()
    
    # async def Proxy_talk(self, websocket, message):
    #     try:
    #         if isinstance(message, str):
    #             message = json.loads(message)
    #         from app.Proxy_talk.proxy_main import Proxy_talk  # 延迟导入（依赖 requests extra）
    #         await Proxy_talk(websocket, message).handle_event()
    #     except Exception as e:
    #         import traceback
    #         traceback.print_exc()
