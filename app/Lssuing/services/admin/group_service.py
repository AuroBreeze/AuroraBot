from datetime import datetime
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from config.env import TIMEZONE
from app.permission import permission_service

class GroupService_admin_API:
    """1级（系统管理员）群组服务层：群组授权管理"""
    def __init__(self, websocket, message):
        self.logger = Logger("Lssuing_group_service")
        self.service = GroupService()
        self.websocket = websocket
        self.message = message
    async def handle_event(self) -> None:
        """
        统一处理各种事件
        """
        if self.message.get("message_type") != "group":
            return
        for handler in (
            self.service.authorize_group,
            self.service.remove_authorization,
            self.service.check_group_list_and_kick,
            self.service.help_service,
        ):
            judge, msg = await handler(self.message)
            if msg is not None:
                await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)

class GroupService:
    """1级权限，群组服务层，封装所有群组相关业务逻辑"""

    def __init__(self):
        self.logger = Logger("Lssuing_group_service")
        self.bj_tz = pytz.timezone(TIMEZONE)

    async def authorize_group(self, message) -> tuple[bool, str]:
        """处理群组授权"""
        msg = str(message.get("raw_message"))
        if not msg.startswith("subscribe_group "):
            self.logger.debug("无效的群组授权格式")
            return False, None

        user_id = str(message.get("user_id"))

        # 解析授权数据
        data = {}
        for line in msg.split("\n"):
            parts = line.strip().split(" ")
            if len(parts) != 2:
                continue
            data[parts[0]] = parts[1]

        # 验证必要参数
        required_fields = ['subscribe_group', 'starttime', 'endtime', 'user_id', 'features']
        if not all(field in data for field in required_fields):
            return False, "缺少必要的授权参数"

        try:
            endtime_days = int(data['endtime'])
        except ValueError:
            return False, "endtime 必须是整数天数"

        # 权限与时间校验由权限门面统一完成
        return permission_service.subscribe_group(
            operator_id=user_id,
            target_group=data['subscribe_group'],
            owner_id=data['user_id'],
            start_time=data['starttime'],
            end_time_days=endtime_days,
            features=data['features'],
        )

    async def remove_authorization(self, message) -> tuple[bool, str]:
        """删除群组授权"""
        msg = str(message.get("raw_message"))
        if not msg.startswith("unsubscribe_group "):
            self.logger.debug("无效的取消授权命令格式")
            return False, None

        user_id = str(message.get("user_id"))
        parts = msg.split(" ")
        if len(parts) < 2:
            return False, "格式: unsubscribe_group <target_group_id>"
        target_group = parts[1]

        return permission_service.unsubscribe_group(user_id, target_group)

    async def check_group_list_and_kick(self, message) -> tuple[bool, str]:
        """
        检查群组列表并踢出不在授权列表中的群组
        """
        try:
            msg = str(message.get("raw_message"))
            if msg != "check_group_list":
                self.logger.debug(f"收到无效命令: {msg}")
                return False, None

            user_id = str(message.get("user_id"))
            self.logger.info(f"开始检查群组列表，请求用户: {user_id}")

            groups_list, db_error = permission_service.list_groups(user_id)
            if db_error:
                self.logger.warning(f"用户 {user_id} 无权限执行此操作: {db_error}")
                return False, db_error

            if not groups_list:
                self.logger.info("当前无授权群组")
                return True, "当前无授权群组"

            # 检查并处理所有群组状态
            current_time = datetime.now(self.bj_tz)
            kicked_groups = []
            warning_groups = []
            normal_groups = []

            for group_id, starttime, endtime in groups_list:
                try:
                    end_dt = datetime.strptime(endtime, "%Y-%m-%d %H:%M:%S").replace(tzinfo=self.bj_tz)
                    remaining_days = (end_dt - current_time).days

                    if remaining_days <= 0:
                        # 已过期群组：静默移除，失败仅记日志（不再把错误文本发回目标群）
                        judge, kick_msg = permission_service.kick_group(user_id, group_id)
                        if not judge:
                            self.logger.error(f"踢出过期群组 {group_id} 失败: {kick_msg}")
                        kicked_groups.append(f"{group_id}(已过期)")
                        self.logger.info(f"已踢出过期群组: {group_id}")
                    elif remaining_days <= 3:
                        # 即将过期群组
                        warning_groups.append(f"{group_id}(剩余{remaining_days}天)")
                    else:
                        # 正常群组
                        normal_groups.append(f"{group_id}(剩余{remaining_days}天)")
                except Exception as e:
                    self.logger.error(f"处理群组 {group_id} 时出错: {e}", exc_info=True)
                    continue

            # 生成结果消息
            result_msg = []
            if kicked_groups:
                result_msg.append(f"⚠️ 已踢出过期群组: {', '.join(kicked_groups)}")
            if warning_groups:
                result_msg.append(f"⚠️ 即将过期群组(3天内): {', '.join(warning_groups)}")

            # 总是显示所有正常群组
            if normal_groups:
                result_msg.append("✅ 正常授权群组:")
                result_msg.append("\n".join([f"  - {group}" for group in normal_groups]))
            elif not kicked_groups and not warning_groups:
                result_msg.append("当前无任何授权群组")

            return True, "\n".join(result_msg)

        except Exception as e:
            self.logger.error(f"检查群组列表时发生未知错误: {e}", exc_info=True)
            return False, "系统错误，请稍后再试"

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

        msg = "Admin 群组服务(group_service)指令菜单:\n" \
              "1. subscribe_group <target_group_id>\nstarttime now\nendtime <days:int>\nuser_id <target_user_id>\nfeatures all - 添加群组授权\n" \
              "2. unsubscribe_group <target_group_id> - 取消群组授权\n" \
              "3. check_group_list - 检查并踢出过期授权群\n"

        return True, msg

    async def send_group_message(self, websocket, group_id, message):
        """发送群消息"""
        await QQAPI_list(websocket).send_group_message(group_id, message)
