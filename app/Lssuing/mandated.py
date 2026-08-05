from api.Logger_owner import Logger
from .services.admin.group_service import GroupService_admin_API
from .services.admin.user_service import UserService_admin_API
from .services.user.group_service import GroupService_user_API
from .services.user.user_service import UserService_user_API

class Mandated():
    """
    管理所有授权的功能（消息入口）
    """
    def __init__(self, websocket, message):
        self.logger = Logger("Lssuing_mandated_group")
        self.websocket = websocket
        self.message = message
        
    async def handle_event(self):
        """
        群组权限管理和群组用户权限管理
        """
        # help 只由管理员群组服务响应一次，避免 4 个 service 各回一条消息
        raw = str(self.message.get("raw_message", ""))
        if raw.strip() == "help":
            await GroupService_admin_API(self.websocket, self.message).handle_event()
            return
        await Manage_authorization_API(self.websocket, self.message).handle_event()


class Manage_authorization_API():
    """ 
    权限管理接口
    """
    def __init__(self, websocket, message):
        self.Logger = Logger("Lssuing_manage_group_authorization")
        self.message = message
        self.websocket = websocket

    async def handle_event(self) -> tuple[bool, str]:
        await GroupService_admin_API(self.websocket, self.message).handle_event()
        await UserService_admin_API(self.websocket, self.message).handle_event()
        await GroupService_user_API(self.websocket, self.message).handle_event()
        await UserService_user_API(self.websocket, self.message).handle_event()
