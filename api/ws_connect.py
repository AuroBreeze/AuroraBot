import websockets
from api.Logger_owner import Logger # 美化日志输出
from api.Share_date import Raw_data # 导入原始数据队列
import asyncio
from api.Msg_dispatcher import Main_dispatcher_and_run
from config.env import WS_URL

class Websocket_receiver:
    def __init__(self):
        self.logger = Logger("Websocket_receiver")  # 实例化日志类
        self.url = WS_URL  # 使用Docker服务名称代替localhost

    async def msg_raw_receiver(self):
        self.logger.info("Starting Websocket Receiver")
        self.logger.info("Websocket URL: %s"% self.url)

        try:
            async with websockets.connect(self.url) as websocket:
                self.logger.info("Websocket Connected: %s" % "QQbot_server_started")
                
                async for message in websocket:
                    self.logger.info("Message Received: %s" % message)
                    await Raw_data.put(message)
                    await Main_dispatcher_and_run().handle_event(websocket, message)

        except Exception as e:
            self.logger.error("Websocket Receiver Error: %s" % e)
        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.error("Websocket Connection Closed Error: %s" % e)
        except:
            self.logger.error("Websocket Receiver Error: %s" % "Unknown Error or closed()")

    async def initialize(self):
        await self.msg_raw_receiver()
    async def start_receiver(self):
        await self.msg_raw_receiver()
if __name__ == '__main__':
    asyncio.run(Websocket_receiver().start_receiver())
