from datetime import datetime
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from config.env import TIMEZONE
from app.permission import permission_service
from app.permission.constants import LEVEL_OWNER

class GroupService:
    """1级（系统管理员）群组服务层：群组授权管理（命令 handler，不负责发送）"""

    def __init__(self):
        self.logger = Logger("Lssuing_group_service")
        self.bj_tz = pytz.timezone(TIMEZONE)

    async def _find_group_owner(self, websocket, group_id) -> str | None:
        """查询真实群主 QQ（role=owner）；查询失败返回 None 不影响主流程"""
        try:
            members = await QQAPI_list(websocket).get_group_member_list(group_id)
            for member in members:
                if member.get("role") == "owner":
                    return str(member.get("user_id"))
        except Exception as e:
            self.logger.error(f"查询群 {group_id} 群主失败: {e}")
        return None

    async def _auto_grant_group_owner(self, websocket, operator_id, target_group, owner_id) -> None:
        """
        混合授权模式：自动识别真实群主并授予 2 级权限（与显式获权用户不同时）。
        查询/授权失败仅告警，不阻断主流程。
        """
        group_owner = await self._find_group_owner(websocket, target_group)
        if group_owner and group_owner != owner_id:
            judge, msg = permission_service.admin_raise_user(operator_id, target_group, group_owner, LEVEL_OWNER)
            if judge:
                self.logger.info(f"群主 {group_owner} 已自动获得群 {target_group} 的 2 级权限")
            else:
                self.logger.warning(f"群主 {group_owner} 自动授权失败: {msg}")

    async def authorize_group(self, websocket, message) -> tuple[bool, str]:
        """处理群组授权（完整版，多行参数）"""
        msg = str(message.get("raw_message"))
        parts = msg.split()
        if not parts or parts[0] not in ("/subscribe_group", "subscribe_group", "subscribe"):
            self.logger.debug("无效的群组授权格式")
            return False, None

        user_id = str(message.get("user_id"))

        # 解析授权数据：首行取目标群号，其余行按 key value 解析
        target_group = parts[1] if len(parts) > 1 else ""
        data = {"subscribe_group": target_group}
        for line in msg.split("\n")[1:]:
            line_parts = line.strip().split(" ")
            if len(line_parts) != 2:
                continue
            data[line_parts[0]] = line_parts[1]

        # 验证必要参数
        required_fields = ['subscribe_group', 'starttime', 'endtime', 'user_id', 'features']
        if not all(field in data for field in required_fields):
            return False, "缺少必要的授权参数"

        try:
            endtime_days = int(data['endtime'])
        except ValueError:
            return False, "endtime 必须是整数天数"

        # 权限与时间校验由权限门面统一完成
        judge, result = permission_service.subscribe_group(
            operator_id=user_id,
            target_group=data['subscribe_group'],
            owner_id=data['user_id'],
            start_time=data['starttime'],
            end_time_days=endtime_days,
            features=data['features'],
        )
        if judge:
            # 混合模式：自动授予真实群主 2 级权限
            await self._auto_grant_group_owner(websocket, user_id, data['subscribe_group'], data['user_id'])
        return judge, result

    async def authorize_group_simple(self, websocket, message) -> tuple[bool, str]:
        """
        简单版群授权：/sub_group <目标群号> <天数> [获权用户]
        默认 starttime=now、features=all；获权用户缺省为命令执行者
        """
        msg = str(message.get("raw_message"))
        parts = msg.split()
        if not parts or parts[0] not in ("/sub_group", "sub_group"):
            self.logger.debug("无效的简单版群授权命令格式")
            return False, None
        if len(parts) < 3:
            return False, "格式: /sub_group <目标群号> <天数> [获权用户]"
        target_group = parts[1]
        try:
            days = int(parts[2])
        except ValueError:
            return False, "天数必须是整数"
        if days < -1:
            return False, "天数不能小于 -1（-1 表示无限期订阅）"
        owner_id = parts[3] if len(parts) > 3 else str(message.get("user_id"))
        operator_id = str(message.get("user_id"))

        judge, result = permission_service.subscribe_group(
            operator_id=operator_id,
            target_group=target_group,
            owner_id=owner_id,
            start_time="now",
            end_time_days=days,
            features="all",
        )
        if judge:
            # 混合模式：自动授予真实群主 2 级权限
            await self._auto_grant_group_owner(websocket, operator_id, target_group, owner_id)
        return judge, result

    async def remove_authorization(self, websocket, message) -> tuple[bool, str]:
        """删除群组授权"""
        msg = str(message.get("raw_message"))
        parts = msg.split()
        if not parts or parts[0] not in ("/unsub", "unsub", "unsubscribe", "unsubscribe_group"):
            self.logger.debug("无效的取消授权命令格式")
            return False, None

        user_id = str(message.get("user_id"))
        if len(parts) < 2:
            return False, "格式: /unsub <目标群号>"
        target_group = parts[1]

        return permission_service.unsubscribe_group(user_id, target_group)

    async def check_group_list_and_kick(self, websocket, message) -> tuple[bool, str]:
        """
        检查群组列表并踢出不在授权列表中的群组
        """
        try:
            msg = str(message.get("raw_message"))
            parts = msg.split()
            if not parts or parts[0] not in ("/check_groups", "check_groups", "check_group_list"):
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
                        # 已过期群组：静默移除，失败仅记日志
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
                    self.logger.error(f"处理群组 {group_id} 时出错: {e}")
                    continue

            # 生成结果消息
            result_msg = []
            if kicked_groups:
                result_msg.append(f"⚠️ 已踢出过期群组: {', '.join(kicked_groups)}")
            if warning_groups:
                result_msg.append(f"⚠️ 即将过期群组(3天内): {', '.join(warning_groups)}")

            if normal_groups:
                result_msg.append("✅ 正常授权群组:")
                result_msg.append("\n".join([f"  - {group}" for group in normal_groups]))
            elif not kicked_groups and not warning_groups:
                result_msg.append("当前无任何授权群组")

            return True, "\n".join(result_msg)

        except Exception as e:
            self.logger.error(f"检查群组列表时发生未知错误: {e}")
            return False, "系统错误，请稍后再试"
