import json
from app.Lssuing.mandated import Mandated
from app.Learn_clock.clock_main import Clock_learn
from app.Commodity_lssuing.manage import Manage


class Main_dispatcher_and_run:
    """
    插件功能器,功能接口,用于注册
    """
    def __init__(self):
        self.msg_dispatcher = Msg_dispatcher()
    async def handle_event(self, websocket, message): # 消息处理
        await self.msg_dispatcher.handle_event(websocket, message)
        
class Msg_dispatcher: 
    """
    原始消息分发处理器
    """
    async def handle_event(self, websocket, message): # 事件处理器(功能注册处)
        await self.Learn_clock(websocket, message)
        await self.Lssuing(websocket, message)
        await self.Commodity_lssuing(websocket, message)
    async def Learn_clock(self, websocket, message):
        try:
            if isinstance(message, str):
                message = json.loads(message)
            await Clock_learn(websocket, message).handle_clock()
        except Exception as e:
            import traceback
            traceback.print_exc()
    async def Lssuing(self, websocket, message):
        try:
            if isinstance(message, str):
                message = json.loads(message)
            await Mandated(websocket, message).handle_event()
        except Exception as e:
            import traceback
            traceback.print_exc()
    async def Commodity_lssuing(self, websocket, message):
        try:
            if isinstance(message, str):
                message = json.loads(message)
                await Manage(websocket, message).handle_event()
        except Exception as e:
            import traceback
            traceback.print_exc()
