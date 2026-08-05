from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from app.permission import permission_service, LEVEL_ADMIN

class UserService_user_API:
    """群组服务层，封装用户侧权限管理业务逻辑"""
    def __init__(self, websocket, message):
        self.logger = Logger("Lssuing_group_service")
        self.service = UserService()
        self.websocket = websocket
        self.message = message
    async def handle_event(self) -> None:
        """
        统一处理各种事件
        """
        for handler in (
            self.service.remove_user_permission,
            self.service.raise_user_permission,
            self.service.help_service,
        ):
            judge, msg = await handler(self.message)
            if msg is not None:
                await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)


class UserService:
    """2,3级权限，群组服务层，封装本群用户权限管理业务逻辑"""

    def __init__(self):
        self.logger = Logger("Lssuing_group_service")

    async def remove_user_permission(self, message) -> tuple[bool, str]:
        """
        移除用户权限,仅能移除本群的低一级的其他人
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("remove "):  # remove <target_user_id>
            self.logger.debug("无效的移除用户权限命令格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        parts = msg.split(" ")
        if len(parts) < 2:
            return False, "格式: remove <target_user_id>"
        target_user_id = parts[1]

        judge, msg_or_err = permission_service.remove_user_permission(user_id, group_id, target_user_id)
        if judge:
            return True, f"成功移除用户{target_user_id}的权限"
        return False, msg_or_err

    async def raise_user_permission(self, message) -> tuple[bool, str]:
        """
        提升用户权限,仅能提升本群的低一级的其他人
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("raise "):  # raise <target_user_id>
            self.logger.debug("无效的提升用户权限命令格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        parts = msg.split(" ")
        if len(parts) < 2:
            return False, "格式: raise <target_user_id>"
        target_user_id = parts[1]

        # 2 级用户在本群内将目标提升为 3 级；目标校验由权限门面完成
        judge, msg_or_err = permission_service.add_user_permission(
            user_id, group_id, target_user_id, LEVEL_ADMIN
        )
        if judge:
            return True, f"成功提升用户{target_user_id}的权限"
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

        msg = "User 用户服务(user_service)指令菜单:\n" \
              "1. remove <target_user_id> - 移除用户权限\n" \
              "2. raise <target_user_id> - 提升用户权限\n"
        return True, msg

    async def send_group_message(self, websocket, group_id, message):
        """发送群消息"""
        await QQAPI_list(websocket).send_group_message(group_id, message)
    async def send_at_group_msg(self, websocket, group_id, user_id, message):
        """
        发送群聊at消息
        """
        await QQAPI_list(websocket).send_at_group_message(group_id, user_id, message)
