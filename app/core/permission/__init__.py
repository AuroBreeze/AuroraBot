"""
统一权限底座（app/permission）

其他 app 接入方式：
    from app.core.permission import permission_service

    # 检查用户权限（数字越小权限越高，1=管理员 2=群主 3=群管理员）
    permission_service.check_user_permission(group_id, user_id, required_level=3)

    # 检查群组是否在授权期内（后台任务执行前调用）
    permission_service.check_group_authorized(group_id)

    # 检查是否系统管理员
    permission_service.is_admin(user_id)

权限数据：./store/db/store_db.db（表结构与旧版 Lssuing 兼容，存量数据直接可用）
"""
from config.env import QQ_ADMIN
from api.Logger_owner import Logger

from .service import PermissionService
from .constants import LEVEL_SYSTEM, LEVEL_OWNER, LEVEL_ADMIN, LEVEL_NONE

# 进程级单例：所有 app 共享同一权限服务（单连接 + WAL）
permission_service = PermissionService()

# 启动校验：播种配置中的初始管理员；为空时告警（权限系统将无人可管理）
if QQ_ADMIN:
    permission_service.store.seed_admin(QQ_ADMIN)
else:
    Logger("permission_init").warning(
        "QQ_ADMIN 未配置！权限系统将没有初始管理员，subscribe_group 等管理命令不可用。"
        "请在 config/_config.yml 的 basic_settings.QQbot_admin_account 配置管理员账号。"
    )

__all__ = [
    "permission_service",
    "LEVEL_SYSTEM",
    "LEVEL_OWNER",
    "LEVEL_ADMIN",
    "LEVEL_NONE",
]
