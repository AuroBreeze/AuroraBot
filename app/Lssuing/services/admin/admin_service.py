"""系统管理员管理：/admin set|add|del|list

- set <qq>：写入 config/_config.yml（basic_settings.QQbot_admin_account，Docker 挂载卷持久化）
  + 同步到 admin_users 表（立即生效，无需重启；重启后 seed_admin 用新值，幂等）
- add <qq>：仅添加到 admin_users 表（运行期生效，不落 yml）
- del <qq>：从表移除（至少保留 1 名系统管理员，防止无人可管）
- list：列出全部系统管理员

权限：仅系统管理员可执行（required_level=LEVEL_SYSTEM + 显式 is_admin 双保险）。
"""

import io

import yaml

from api.Logger_owner import Logger
from app.core.permission import permission_service

CONFIG_PATH = "config/_config.yml"


class AdminService:
    def __init__(self):
        self.logger = Logger("admin_service")

    # ---------- 配置持久化 ----------

    def _update_config_admin(self, qq: str) -> tuple[bool, str]:
        """写回 config/_config.yml 的 QQbot_admin_account（持久化到 Docker config 卷）"""
        try:
            cfg = yaml.safe_load(io.open(CONFIG_PATH, encoding="utf-8")) or {}
            cfg.setdefault("basic_settings", {})["QQbot_admin_account"] = str(qq)
            io.open(CONFIG_PATH, "w", encoding="utf-8", newline="").write(
                yaml.dump(cfg, allow_unicode=True, sort_keys=False)
            )
            return True, f"已写入配置 config/_config.yml：QQbot_admin_account = {qq}"
        except Exception as e:
            self.logger.error(f"写入 _config.yml 失败: {e}")
            return False, f"写入配置失败: {e}"

    # ---------- 命令入口 ----------

    async def admin_handler(self, websocket, message) -> tuple[bool, str]:
        """解析 /admin 子命令"""
        operator = str(message.get("user_id", ""))
        if not permission_service.is_admin(operator):
            return True, "仅系统管理员可执行此操作"

        parts = str(message.get("raw_message", "")).split()
        if len(parts) < 2:
            return True, "用法：/admin set <qq> | add <qq> | del <qq> | list"
        action = parts[1]
        qq = parts[2] if len(parts) > 2 else ""

        if action == "list":
            admins = permission_service.store.list_admins()
            text = f"系统管理员（{len(admins)} 人）：\n" + "\n".join(
                f"{i}. {a}" for i, a in enumerate(admins, 1)
            ) if admins else "暂无系统管理员"
            return True, text

        if action in ("set", "add", "del"):
            if not qq.isdigit():
                return True, "QQ 号需为纯数字"
            store = permission_service.store

            if action == "set":
                ok_cfg, msg_cfg = self._update_config_admin(qq)
                ok_db, msg_db = store.add_admin(qq, remark="命令设置主管理员")
                return True, f"{msg_cfg}\n{msg_db}"
            if action == "add":
                ok, msg = store.add_admin(qq, remark="命令添加")
                return True, msg
            if action == "del":
                admins = store.list_admins()
                if len(admins) <= 1:
                    return True, "至少保留一名系统管理员，拒绝移除"
                ok, msg = store.remove_admin(qq)
                if ok and not store.is_admin(qq):
                    msg += "\n该账号已无法使用管理命令"
                return True, msg

        return True, f"未知操作：{action}（支持 set/add/del/list）"
