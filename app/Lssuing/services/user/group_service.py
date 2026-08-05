from api.Logger_owner import Logger
from app.permission import permission_service

class GroupService:
    """2,3级权限，群组服务层：用户侧群组查询（命令 handler，不负责发送）"""

    def __init__(self):
        self.logger = Logger("Lssuing_group_service")

    async def list_user_permissions(self, message) -> tuple[bool, str]:
        """
        列出群组所有的授权用户（仅限本群用户或系统管理员，防跨群枚举）
        """
        msg = str(message.get("raw_message"))
        parts = msg.split()
        if not parts or parts[0] not in ("/list_users", "list_users", "list_user"):
            self.logger.debug("无效的列出群组授权用户命令格式")
            return False, None

        user_id = str(message.get("user_id"))
        if len(parts) < 2:
            return False, "格式: /list_users <目标群号>"
        target_group_id = parts[1]

        user_list, msg_or_err = permission_service.list_group_users(user_id, target_group_id)
        if msg_or_err:
            return False, msg_or_err

        if not user_list:
            return False, f"群组 {target_group_id} 暂无授权用户"

        header = "\n授权用户\t等级\t父级ID"
        rows = "\n".join(f"{user}\t{level}\t{parent}" for user, level, parent in user_list)
        return True, f"{header}\n{rows}"

    async def check_group_information(self, message) -> tuple[bool, str]:
        """
        检查群组信息
        """
        msg = str(message.get("raw_message"))
        parts = msg.split()
        if not parts or parts[0] not in ("/group_info", "group_info"):
            self.logger.debug("无效的检查群组权限命令格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))

        result, msg_or_err = permission_service.get_group_info(user_id, group_id)
        if result:
            # result: (id, group_id, user_id, start_time, end_time, features, create_time)
            info = f"群组: {group_id}\n管理员: {result[2]}\n创建时间: {result[3]}\n到期时间: {result[4]}\n群组权限: {result[5]}"
            return True, info
        return False, msg_or_err
