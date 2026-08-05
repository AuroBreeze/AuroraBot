"""
权限服务门面（app/permission/service.py）

其他 app 的唯一接入点：from app.permission import permission_service

所有管理操作显式携带操作者（operator_id），在门面内完成鉴权，
避免各调用方各自拼装权限检查造成不一致或绕过。
"""
from .constants import LEVEL_SYSTEM, LEVEL_OWNER, LEVEL_ADMIN, LEVEL_NONE, TIME_FORMAT
from .store import PermissionStore
from api.Logger_owner import Logger
from datetime import datetime, timedelta


class PermissionService:
    """统一权限服务：查询与管理的门面"""

    def __init__(self, store: PermissionStore = None):
        self.logger = Logger("permission_service")
        self.store = store if store is not None else PermissionStore()

    # ---------- 只读查询（其他 app 使用） ----------

    def check_user_permission(self, group_id, user_id, required_level: int = LEVEL_ADMIN) -> bool:
        """检查 user_id 在 group_id 是否拥有 >= required_level 权限（数字越小越高）"""
        return self.store.check_user_permission(group_id, user_id, required_level)

    def check_group_authorized(self, group_id) -> bool:
        """群组是否处于授权期内（供后台任务如定时喊话执行前检查）"""
        judge, _ = self.store.check_group_permission(group_id)
        return judge

    def is_admin(self, user_id) -> bool:
        """是否系统管理员"""
        return self.store.is_admin(user_id)

    def get_user_level(self, group_id, user_id) -> tuple[int, str]:
        """获取用户在群内的权限级别"""
        return self.store.get_user_permission_level(group_id, user_id)

    def get_user_groups(self, user_id) -> tuple[list, str]:
        """获取用户归属的群列表"""
        return self.store.get_user_ascription(user_id)

    # ---------- 群组授权（仅系统管理员） ----------

    def subscribe_group(self, operator_id, target_group, owner_id,
                        start_time: str, end_time_days: int, features: str) -> tuple[bool, str]:
        """
        登记授权群并写入授权时间段。start_time 为 'now' 或 '%Y-%m-%d %H:%M:%S'。
        end_time_days 为授权天数（>= 0）；-1 表示无限期订阅（永不过期）。
        """
        if not self.store.is_admin(operator_id):
            return False, f"用户{operator_id}不是系统管理员，无权授权群组"

        # 时间参数校验
        try:
            if start_time == "now":
                start_dt = datetime.now()
            else:
                start_dt = datetime.strptime(start_time, TIME_FORMAT)
            if end_time_days == -1:
                # 无限期订阅：结束时间设为极大值，判定逻辑自然永不过期
                end_dt = datetime(9999, 12, 31, 23, 59, 59)
            elif end_time_days < -1:
                return False, "授权天数不能为负数（-1 表示无限期订阅）"
            else:
                end_dt = start_dt + timedelta(days=end_time_days)
        except ValueError:
            return False, f"时间格式错误，应为 {TIME_FORMAT} 或 now"

        start_str = start_dt.strftime(TIME_FORMAT)
        end_str = end_dt.strftime(TIME_FORMAT)

        if not self.store.create_group_permission(target_group, owner_id, operator_id, LEVEL_OWNER):
            return False, "群组登记失败"
        return self.store.add_group_authorization(target_group, owner_id, start_str, end_str, features)

    def unsubscribe_group(self, operator_id, group_id) -> tuple[bool, str]:
        """取消群组授权（级联删除该群全部用户权限）"""
        if not self.store.is_admin(operator_id):
            return False, f"用户{operator_id}不是系统管理员，无权取消授权"
        judge, msg = self.store.remove_authorize_group(group_id)
        return (True, f"已取消群组 {group_id} 的授权") if judge else (False, msg)

    def list_groups(self, operator_id) -> tuple[list, str]:
        """列出全部授权群（仅系统管理员）"""
        if not self.store.is_admin(operator_id):
            return [], f"用户{operator_id}不是系统管理员"
        return self.store.list_group_permissions()

    def kick_group(self, operator_id, group_id) -> tuple[bool, str]:
        """移除单个授权群（仅系统管理员）"""
        if not self.store.is_admin(operator_id):
            return False, f"用户{operator_id}不是系统管理员"
        return self.store.kick_unpermission_group(group_id)

    # ---------- 用户权限管理 ----------

    def add_user_permission(self, operator_id, group_id, target_user_id, level: int = LEVEL_ADMIN) -> tuple[bool, str]:
        """本群内提权：operator 需 2 级，且目标级别必须低于 operator（防提权/防覆盖降级）"""
        if not self.store.check_user_permission(group_id, operator_id, LEVEL_OWNER):
            return False, f"用户{operator_id}需要2级权限"
        return self.store.add_user_authorization(group_id, target_user_id, level, operator_id)

    def admin_raise_user(self, operator_id, group_id, target_user_id, level: int = LEVEL_ADMIN) -> tuple[bool, str]:
        """跨群提权（系统管理员专用）：operator 无需在目标群有记录"""
        if not self.store.is_admin(operator_id):
            return False, f"用户{operator_id}不是系统管理员"
        return self.store.add_user_authorization(group_id, target_user_id, level, operator_id)

    def remove_user_permission(self, operator_id, group_id, target_user_id) -> tuple[bool, str]:
        """移除用户权限：operator 需能管理 target（或为系统管理员）"""
        return self.store.remove_user_permission(group_id, operator_id, target_user_id)

    def list_group_users(self, requester_id, group_id) -> tuple[list, str]:
        """列出群授权用户：仅限本群用户或系统管理员（修复跨群枚举）"""
        if self.store.is_admin(requester_id):
            return self.store.list_group_users(group_id)
        groups, _ = self.store.get_user_ascription(requester_id)
        if str(group_id) not in groups:
            return [], f"用户{requester_id}不属于群组{group_id}，无权查看"
        return self.store.list_group_users(group_id)

    def get_group_info(self, requester_id, group_id) -> tuple[object, str]:
        """查看群组授权信息（归属校验）"""
        return self.store.get_group_information(group_id, requester_id)

    # ---------- 系统管理员管理 ----------

    def add_admin(self, operator_id, user_id, remark: str = "") -> tuple[bool, str]:
        """添加系统管理员（仅系统管理员可操作）"""
        if not self.store.is_admin(operator_id):
            return False, f"用户{operator_id}不是系统管理员"
        return self.store.add_admin(user_id, remark)

    def remove_admin(self, operator_id, user_id) -> tuple[bool, str]:
        """移除系统管理员（仅系统管理员可操作）"""
        if not self.store.is_admin(operator_id):
            return False, f"用户{operator_id}不是系统管理员"
        return self.store.remove_admin(user_id)

    def list_admins(self, operator_id) -> tuple[list, str]:
        """列出系统管理员（仅系统管理员可操作）"""
        if not self.store.is_admin(operator_id):
            return [], f"用户{operator_id}不是系统管理员"
        return self.store.list_admins(), ""
