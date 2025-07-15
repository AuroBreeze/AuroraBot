from api.Logger_owner import Logger
from .admin.commodity_manage import GroupService_admin_API
from .purchaser.user_permissions import UserService_user_API

class Manage():
    def __init__(self, websocket, message):
        self.logger = Logger("Commodity_manage")
        self.websocket = websocket
        self.message = message
        
    async def handle_event(self):
        await Manage_authorization_API(self.websocket, self.message).handle_event()


class Manage_authorization_API():
    def __init__(self, websocket, message):
        self.Logger = Logger("Lssuing_manage_group_authorization")
        self.message = message
        self.websocket = websocket

    async def handle_event(self) -> tuple[bool, str]:
        await GroupService_admin_API(self.websocket, self.message).handle_event()
        await UserService_user_API(self.websocket, self.message).handle_event()