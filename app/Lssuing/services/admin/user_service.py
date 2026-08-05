from api.Logger_owner import Logger
from app.core.permission import permission_service

class UserService:
    """用户权限管理（1级：跨群提权/移除，命令 handler，不负责发送）"""

    def __init__(self):
        self.logger = Logger("Lssuing_user_service")

    async def raise_user_permission(self, websocket, message) -> tuple[bool, str]:
        """改变用户群组权限（跨群，仅系统管理员）"""
        msg = str(message.get("raw_message"))
        parts = msg.split()
        if not parts or parts[0] not in ("/grant", "grant", "raise_user"):
            self.logger.debug("无效的权限提高命令格式")
            return False, None

        user_id = str(message.get("user_id"))
        if len(parts) < 4:
            return False, "格式: /grant <目标群号> <目标用户> <level>"
        target_group_id, target_user = parts[1], parts[2]
        try:
            level = int(parts[3])
        except ValueError:
            return False, "level 必须是整数(2或3)"

        return permission_service.admin_raise_user(user_id, target_group_id, target_user, level)

    async def remove_user_permission(self, websocket, message) -> tuple[bool, str]:
        """取消用户权限（跨群，仅系统管理员）"""
        msg = str(message.get("raw_message"))
        parts = msg.split()
        if not parts or parts[0] not in ("/remove_user", "remove_user"):
            self.logger.debug("无效的移除权限命令格式")
            return False, None

        user_id = str(message.get("user_id"))
        if len(parts) < 3:
            return False, "格式: /remove_user <目标群号> <目标用户>"
        target_group_id, target_user_id = parts[1], parts[2]

        judge, msg_or_err = permission_service.remove_user_permission(user_id, target_group_id, target_user_id)
        if judge:
            return True, f"已取消群组 {target_group_id} 的用户 {target_user_id} 的权限"
        return False, msg_or_err
