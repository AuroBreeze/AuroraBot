"""
权限核心存储层（app/permission/store.py）

设计要点：
- 进程内共享单个 sqlite 连接（WAL + check_same_thread=False），避免每条消息新建连接
- 表结构与旧版 app/Lssuing 完全兼容（group_permissions / user_permissions / group_information），
  存量数据无需迁移；新增 admin_users 多管理员表
- 修复历史漏洞：DELETE 语法、时间比较、提权覆盖、跨群枚举、群授权失效
"""
import os
import sqlite3
from datetime import datetime

import pytz

from api.Logger_owner import Logger
from config.env import TIMEZONE, QQ_ADMIN
from .constants import LEVEL_SYSTEM, LEVEL_OWNER, LEVEL_ADMIN, LEVEL_NONE, TIME_FORMAT

# 默认数据库路径（与旧版一致，兼容存量数据）
DEFAULT_DB_PATH = os.path.join("store", "db", "store_db.db")


class PermissionStore:
    """权限数据存取层：所有权限判定与管理操作的唯一数据来源"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.logger = Logger("permission_store")
        self.db_path = db_path
        self.bj_tz = pytz.timezone(TIMEZONE)
        self.conn = None

    # ---------- 连接与建表 ----------

    def _get_connection(self) -> sqlite3.Connection:
        if self.conn is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA journal_mode = WAL")
            self._init_dbs()
        return self.conn

    def _init_dbs(self) -> None:
        cursor = self.conn.cursor()

        # 授权群组表（兼容旧版）
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_permissions (
            group_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id)
        )
        """)

        # 群用户权限表（兼容旧版）
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            level INTEGER NOT NULL,
            parent_id TEXT,
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES group_permissions(group_id) ON DELETE CASCADE,
            UNIQUE (group_id, user_id)
        )
        """)

        # 群组授权信息表（兼容旧版）
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_information (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME NOT NULL,
            features TEXT NOT NULL,
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES group_permissions(group_id) ON DELETE CASCADE,
            UNIQUE (group_id)
        )
        """)

        # 多管理员表（新增）
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            user_id TEXT PRIMARY KEY,
            remark TEXT DEFAULT '',
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_auth_group ON group_information(group_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_auth_user ON group_information(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_auth_time ON group_information(start_time, end_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_perm_group ON user_permissions(group_id)")

        self.conn.commit()

    # ---------- 时间工具 ----------

    def _now_str(self) -> str:
        """当前时间，统一为无时区定长字符串"""
        return datetime.now(self.bj_tz).strftime(TIME_FORMAT)

    @staticmethod
    def _parse_dt(text: str) -> datetime:
        """解析统一格式的时间字符串（naive）"""
        return datetime.strptime(text, TIME_FORMAT)

    # ---------- 系统管理员（多管理员表） ----------

    def is_admin(self, user_id) -> bool:
        """user_id 是否为系统管理员（查 admin_users 表）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM admin_users WHERE user_id = ?", (str(user_id),))
            return cursor.fetchone() is not None
        except Exception as e:
            self.logger.error(f"检查管理员失败: {e}")
            return False

    def seed_admin(self, user_id: str, remark: str = "config QQ_ADMIN") -> None:
        """播种初始管理员（幂等）：启动时用配置的 QQ_ADMIN 初始化"""
        if not user_id:
            return
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO admin_users (user_id, remark) VALUES (?, ?)",
            (str(user_id), remark),
        )
        conn.commit()

    def add_admin(self, user_id: str, remark: str = "") -> tuple[bool, str]:
        """添加系统管理员"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO admin_users (user_id, remark) VALUES (?, ?)",
                (str(user_id), remark),
            )
            conn.commit()
            return True, f"管理员 {user_id} 添加成功"
        except Exception as e:
            self.logger.error(f"添加管理员失败: {e}")
            return False, f"添加管理员失败: {e}"

    def remove_admin(self, user_id: str) -> tuple[bool, str]:
        """移除系统管理员"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admin_users WHERE user_id = ?", (str(user_id),))
            conn.commit()
            return True, f"管理员 {user_id} 已移除"
        except Exception as e:
            self.logger.error(f"移除管理员失败: {e}")
            return False, f"移除管理员失败: {e}"

    def list_admins(self) -> list[str]:
        """列出全部系统管理员"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM admin_users ORDER BY create_time")
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"列出管理员失败: {e}")
            return []

    # ---------- 权限判定 ----------

    def check_user_permission(self, group_id, user_id, required_level: int = LEVEL_ADMIN) -> bool:
        """检查用户是否拥有 >= required_level 的权限（数字越小权限越高）"""
        try:
            if self.is_admin(user_id):
                return True
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT level FROM user_permissions WHERE group_id = ? AND user_id = ?",
                (str(group_id), str(user_id)),
            )
            result = cursor.fetchone()
            if result is None:
                return False
            return result[0] <= required_level
        except Exception as e:
            self.logger.error(f"检查用户权限失败: {e}")
            return False

    def get_user_permission_level(self, group_id, user_id) -> tuple[int, str]:
        """获取用户在某群的权限级别；系统管理员恒为 LEVEL_SYSTEM"""
        try:
            if self.is_admin(user_id):
                return LEVEL_SYSTEM, None
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT level FROM user_permissions WHERE group_id = ? AND user_id = ?",
                (str(group_id), str(user_id)),
            )
            result = cursor.fetchone()
            if result is None:
                return LEVEL_NONE, f"用户{user_id}在群组{group_id}中没有权限记录"
            return result[0], None
        except Exception as e:
            self.logger.error(f"查询用户权限等级失败: {e}")
            return -1, f"查询用户权限等级失败: {e}"

    def can_manage_user(self, group_id, manager_id, target_user_id) -> bool:
        """manager_id 是否有权管理 target_user_id（仅当目标存在时才有意义）"""
        try:
            if self.is_admin(manager_id):
                return True
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT level FROM user_permissions WHERE group_id = ? AND user_id = ?",
                (str(group_id), str(manager_id)),
            )
            manager_row = cursor.fetchone()
            if manager_row is None:
                return False
            manager_level = manager_row[0]

            cursor.execute(
                "SELECT level FROM user_permissions WHERE group_id = ? AND user_id = ?",
                (str(group_id), str(target_user_id)),
            )
            target_row = cursor.fetchone()
            if target_row is None:
                return False  # 目标无权限记录，无从管理
            target_level = target_row[0]

            # 数字越小权限越高：manager 的级别必须严格高于（数字小于）目标
            if manager_level >= target_level:
                return False
            return (manager_level == LEVEL_SYSTEM and target_level in (LEVEL_OWNER, LEVEL_ADMIN)) or \
                   (manager_level == LEVEL_OWNER and target_level == LEVEL_ADMIN)
        except Exception as e:
            self.logger.error(f"检查管理权限失败: {e}")
            return False

    # ---------- 用户授权管理 ----------

    def add_user_authorization(self, group_id, user_id, level: int, parent_id) -> tuple[bool, str]:
        """
        添加/更新用户权限。防提权规则：
        - level 只能为 2 或 3
        - 目标用户已存在时，若其现有级别不低（数字 <= level）则拒绝覆盖（防同级/高等级被降级）
        - 授权者 parent_id 必须有 2 级（或为系统管理员）
        """
        try:
            if level <= LEVEL_SYSTEM or level > LEVEL_ADMIN:
                return False, "权限级别错误"

            # 授权者必须持有 2 级或为管理员
            parent_level, _ = self.get_user_permission_level(group_id, parent_id)
            if parent_level == LEVEL_NONE:
                return False, f"用户{parent_id}在群组{group_id}中没有权限记录"
            if parent_level > LEVEL_OWNER:  # 3 级不能授权
                return False, f"用户{parent_id}没有2级权限"

            conn = self._get_connection()
            cursor = conn.cursor()

            # 目标用户现有记录检查（防覆盖降级/同级篡改；系统管理员不受此限）
            cursor.execute(
                "SELECT level FROM user_permissions WHERE group_id = ? AND user_id = ?",
                (str(group_id), str(user_id)),
            )
            existing = cursor.fetchone()
            if existing is not None and not self.is_admin(parent_id):
                existing_level = existing[0]
                if existing_level <= level:
                    return False, f"目标用户{user_id}已有同级或更高权限({existing_level})，拒绝覆盖"
                # 授权者必须能管理目标
                if not self.can_manage_user(group_id, parent_id, user_id):
                    return False, f"用户{parent_id}无权修改用户{user_id}的权限"

            cursor.execute(
                "INSERT OR REPLACE INTO user_permissions (group_id, user_id, level, parent_id) "
                "VALUES (?, ?, ?, ?)",
                (str(group_id), str(user_id), level, str(parent_id)),
            )
            conn.commit()
            return True, f"用户: {user_id} 权限设置成功, 权限等级: {level}, 上级授权人: {parent_id}"
        except Exception as e:
            self.logger.error(f"添加用户授权失败: {e}")
            return False, f"添加用户授权失败: {e}"

    def remove_user_permission(self, group_id, manager_id, target_user_id) -> tuple[bool, str]:
        """移除用户权限（调用方须先鉴权 manager 为管理员或 2 级）"""
        try:
            if not self.can_manage_user(group_id, manager_id, target_user_id):
                return False, f"用户 {manager_id} 无权移除 {target_user_id} 的权限"

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM user_permissions WHERE group_id = ? AND user_id = ?",
                (str(group_id), str(target_user_id)),
            )
            cursor.execute(
                "DELETE FROM group_information WHERE group_id = ? AND user_id = ?",
                (str(group_id), str(target_user_id)),
            )
            conn.commit()
            return True, ""
        except Exception as e:
            self.logger.error(f"移除用户权限失败: {e}")
            return False, f"移除用户权限失败: {e}"

    def list_group_users(self, group_id) -> tuple[list, str]:
        """列出群组所有授权用户（归属校验由调用方完成）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, level, parent_id FROM user_permissions WHERE group_id = ?",
                (str(group_id),),
            )
            return cursor.fetchall(), None
        except Exception as e:
            self.logger.error(f"列出群组用户失败: {e}")
            return [], f"列出群组用户失败: {e}"

    def get_user_ascription(self, user_id) -> tuple[list, str]:
        """获取用户归属的群组列表"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT group_id FROM user_permissions WHERE user_id = ?", (str(user_id),))
            rows = cursor.fetchall()
            if not rows:
                return [], f"用户 {user_id} 没有归属的群组"
            return [row[0] for row in rows], ""
        except Exception as e:
            self.logger.error(f"获取用户归属的群组失败: {e}")
            return [], f"获取用户归属的群组失败: {e}"

    # ---------- 群组授权管理 ----------

    def create_group_permission(self, group_id, owner_id, parent_id, level: int = LEVEL_OWNER) -> bool:
        """登记授权群 + 为群主 owner_id 授予 2 级权限（调用方须为系统管理员）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT COUNT(*) FROM group_permissions WHERE group_id = ?", (str(group_id),)
            )
            if cursor.fetchone()[0] > 0:
                cursor.execute(
                    "UPDATE group_permissions SET owner_id = ? WHERE group_id = ?",
                    (str(owner_id), str(group_id)),
                )
            else:
                cursor.execute(
                    "INSERT INTO group_permissions (group_id, owner_id) VALUES (?, ?)",
                    (str(group_id), str(owner_id)),
                )

            cursor.execute(
                "INSERT OR REPLACE INTO user_permissions (group_id, user_id, level, parent_id) "
                "VALUES (?, ?, ?, ?)",
                (str(group_id), str(owner_id), level, str(parent_id)),
            )
            conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"创建群组权限失败: {e}")
            return False

    def add_group_authorization(self, group_id, user_id, start_time: str, end_time: str, features: str) -> tuple[bool, str]:
        """写入群组授权时间段（调用方负责时间格式校验）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO group_information "
                "(group_id, user_id, start_time, end_time, features) VALUES (?, ?, ?, ?, ?)",
                (str(group_id), str(user_id), start_time, end_time, features),
            )
            conn.commit()
            return True, f"群组{group_id}授权成功,获权用户{user_id}"
        except Exception as e:
            self.logger.error(f"群组授权失败: {e}")
            return False, f"群组授权失败: {e}"

    def remove_authorize_group(self, group_id) -> tuple[bool, str]:
        """删除授权群（先检查是否存在）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM group_permissions WHERE group_id = ?", (str(group_id),))
            if cursor.fetchone()[0] == 0:
                return False, f"群组 {group_id} 不存在于群组授权中"
            cursor.execute("DELETE FROM group_permissions WHERE group_id = ?", (str(group_id),))
            conn.commit()
            return True, None
        except Exception as e:
            self.logger.error(f"删除授权群 {group_id} 失败: {e}")
            return False, f"删除授权群 {group_id} 失败: {e}"

    def check_group_permission(self, group_id) -> tuple[bool, object]:
        """检查群组是否在授权时间段内；返回 (是否有效, 授权记录或错误信息)"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, group_id, user_id, start_time, end_time, features, create_time "
                "FROM group_information WHERE group_id = ? LIMIT 1",
                (str(group_id),),
            )
            result = cursor.fetchone()
            if result is None:
                return False, f"群组{group_id}没有任何授权记录"

            now = datetime.now(self.bj_tz).replace(tzinfo=None)
            try:
                start_dt = self._parse_dt(result[3])
                end_dt = self._parse_dt(result[4])
            except ValueError:
                return False, f"群组{group_id}授权时间格式异常"
            if start_dt <= now <= end_dt:
                return True, result
            return False, f"群组{group_id}授权已过期(授权至 {result[4]})"
        except Exception as e:
            self.logger.error(f"查询群组授权状态失败: {e}")
            return False, f"查询群组授权状态失败: {e}"

    def list_group_permissions(self) -> tuple[list, str]:
        """列出所有授权群组（group_id, start_time, end_time）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT group_id, start_time, end_time FROM group_information")
            return cursor.fetchall(), None
        except Exception as e:
            self.logger.error(f"列出群组失败: {e}")
            return None, f"列出群组失败: {e}"

    def kick_unpermission_group(self, group_id) -> tuple[bool, str]:
        """移除单个授权群（修复旧版 SQL 语法错误）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM group_permissions WHERE group_id = ?", (str(group_id),))
            conn.commit()
            return True, f"已移除群组 {group_id} 的授权状态"
        except Exception as e:
            self.logger.error(f"移除群组 {group_id} 失败: {e}")
            return False, f"移除群组 {group_id} 失败: {e}"

    def get_group_information(self, group_id, user_id) -> tuple[object, str]:
        """获取群组授权信息（归属校验：仅限本群用户或系统管理员）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            if not self.is_admin(user_id):
                cursor.execute(
                    "SELECT 1 FROM user_permissions WHERE group_id = ? AND user_id = ?",
                    (str(group_id), str(user_id)),
                )
                if cursor.fetchone() is None:
                    return None, f"用户{user_id}不属于群组{group_id}"
            cursor.execute(
                "SELECT id, group_id, user_id, start_time, end_time, features, create_time "
                "FROM group_information WHERE group_id = ? LIMIT 1",
                (str(group_id),),
            )
            result = cursor.fetchone()
            if result is None:
                return None, f"群组{group_id}不存在"
            return result, None
        except Exception as e:
            self.logger.error(f"获取群组信息失败: {e}")
            return None, f"获取群组信息失败: {e}"

    def get_manageable_users(self, group_id, manager_id) -> tuple[list, str]:
        """获取 manager_id 可管理的用户列表"""
        try:
            if not self.check_user_permission(group_id, manager_id, LEVEL_OWNER):
                return [], "权限不足"
            conn = self._get_connection()
            cursor = conn.cursor()
            manager_level, _ = self.get_user_permission_level(group_id, manager_id)
            if manager_level == LEVEL_SYSTEM:
                cursor.execute(
                    "SELECT p.user_id, p.level, a.start_time, a.end_time, a.features "
                    "FROM user_permissions p "
                    "JOIN group_information a ON p.group_id = a.group_id AND p.user_id = a.user_id "
                    "WHERE p.group_id = ? AND p.level IN (2, 3)",
                    (str(group_id),),
                )
            else:
                cursor.execute(
                    "SELECT p.user_id, p.level, a.start_time, a.end_time, a.features "
                    "FROM user_permissions p "
                    "JOIN group_information a ON p.group_id = a.group_id AND p.user_id = a.user_id "
                    "WHERE p.group_id = ? AND p.level = 3",
                    (str(group_id),),
                )
            return cursor.fetchall(), ""
        except Exception as e:
            self.logger.error(f"获取可管理用户失败: {e}")
            return [], f"获取可管理用户失败: {e}"

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None
