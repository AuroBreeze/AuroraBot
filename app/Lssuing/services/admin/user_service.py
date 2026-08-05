from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from app.permission import permission_service

class UserService_admin_API:
    """
    群组用户权限服务层,封装admin权限群组用户权限相关功能
    """
    def __init__(self, websocket, message):
        self.logger = Logger("Lssuing_group_service")
        self.service = UserService()
        self.websocket = websocket
        self.message = message
    async def handle_event(self) -> None:
        """
        统一处理各种事件
        """
        if self.message.get("message_type") != "group":
            return

        for handler in (
            self.service.raise_user_permission,
            self.service.remove_user_permission,
            self.service.help_service,
        ):
            judge, msg = await handler(self.message)
            if msg is not None:
                await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)

class UserService:
    """
    用户权限管理（1级：跨群提权/移除）
    """
    def __init__(self):
        self.logger = Logger("Lssuing_user_service")

    async def raise_user_permission(self, message) -> tuple[bool, str]:
        """改变用户群组权限（跨群，仅系统管理员）"""
        msg = str(message.get("raw_message"))
        if not msg.startswith("raise_user "):
            self.logger.debug("无效的权限提高命令格式")
            return False, None

        user_id = str(message.get("user_id"))
        parts = msg.split(" ")
        if len(parts) < 4:
            return False, "格式: raise_user <target_group_id> <target_user> <level>"
        target_group_id, target_user = parts[1], parts[2]
        try:
            level = int(parts[3])
        except ValueError:
            return False, "level 必须是整数(2或3)"

        return permission_service.admin_raise_user(user_id, target_group_id, target_user, level)

    async def remove_user_permission(self, message) -> tuple[bool, str]:
        """取消用户权限（跨群，仅系统管理员）"""
        msg = str(message.get("raw_message"))
        if not msg.startswith("remove_user "):
            self.logger.debug("无效的移除权限命令格式")
            return False, None

        user_id = str(message.get("user_id"))
        parts = msg.split(" ")
        if len(parts) < 3:
            return False, "格式: remove_user <target_group_id> <target_user_id>"
        target_group_id, target_user_id = parts[1], parts[2]

        judge, msg_or_err = permission_service.remove_user_permission(user_id, target_group_id, target_user_id)
        if judge:
            return True, f"已取消群组 {target_group_id} 的用户 {target_user_id} 的权限"
        return False, msg_or_err

    async def help_service(self, message) -> tuple[bool, str]:
        """
        指令菜单
        """
        msg = str(message.get("raw_message"))
        if msg != "help":
            self.logger.debug("无效的群组服务帮助命令格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))

        if not permission_service.check_user_permission(group_id, user_id, 3):
            return False, None  # 权限不足，不发送消息

        msg = "Admin 用户服务(user_service)指令菜单:\n" \
              "1. raise_user <target_group_id> <target_user> <level> - 提升用户群组权限\n" \
              "2. remove_user <target_group_id> <target_user_id> - 移除用户群组权限\n"

        return True, msg

    async def send_group_message(self, websocket, group_id, message):
        """发送群消息"""
        await QQAPI_list(websocket).send_group_message(group_id, message)
