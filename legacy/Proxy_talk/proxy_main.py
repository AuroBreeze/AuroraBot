from config import env
from api.Botapi import Logger
from .admin.command import Command_API


class Proxy_talk:
    def __init__(self,websocket, message):
        self.logger = Logger(log_name='Proxy_main')

        self.websocket = websocket
        self.message = message

    async def handle_event(self):
        await Proxy_talk_handler(self.websocket, self.message).handle_event()

class Proxy_talk_handler:
    def __init__(self,websocket, message):
        self.logger = Logger(log_name='Proxy_handler')
        self.websocket = websocket
        self.message = message

    async def handle_event(self):
        await Command_API(self.websocket, self.message).handle_command()
        pass

