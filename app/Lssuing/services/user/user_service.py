from api.Logger_owner import Logger
from app.core.permission import permission_service, LEVEL_ADMIN

class UserService:
    """2,3级权限，群组服务层：本群用户权限管理（命令 handler，不负责发送）"""

    def __init__(self):
        self.logger = Logger("Lssuing_group_service")

    async def remove_user_permission(self, websocket, message) -> tuple[bool, str]:
        """
        移除用户权限,仅能移除本群的低一级的其他人
        """
        msg = str(message.get("raw_message"))
        parts = msg.split()
        if not parts or parts[0] not in ("/revoke", "revoke"):
            self.logger.debug("无效的移除用户权限命令格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        if len(parts) < 2:
            return False, "格式: /revoke <目标用户>"
        target_user_id = parts[1]

        judge, msg_or_err = permission_service.remove_user_permission(user_id, group_id, target_user_id)
        if judge:
            return True, f"成功移除用户{target_user_id}的权限"
        return False, msg_or_err

    async def raise_user_permission(self, websocket, message) -> tuple[bool, str]:
        """
        提升用户权限,仅能提升本群的低一级的其他人
        """
        msg = str(message.get("raw_message"))
        parts = msg.split()
        if not parts or parts[0] not in ("/promote", "promote"):
            self.logger.debug("无效的提升用户权限命令格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        if len(parts) < 2:
            return False, "格式: /promote <目标用户>"
        target_user_id = parts[1]

        # 2 级用户在本群内将目标提升为 3 级；目标校验由权限门面完成
        judge, msg_or_err = permission_service.add_user_permission(
            user_id, group_id, target_user_id, LEVEL_ADMIN
        )
        if judge:
            return True, f"成功提升用户{target_user_id}的权限"
        return False, msg_or_err
