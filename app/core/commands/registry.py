"""
命令注册中心（app/core/commands/registry.py）

职责：
- register: 注册命令，检测同名/别名冲突（启动告警，不覆盖）
- dispatch: 首词匹配命令 → 统一权限校验 → 调用 handler → 统一发送回复
- help_text: 按调用者权限过滤、按 app 分组的帮助菜单；支持查看单个命令详情

设计原则：
- 其他 app 通过装饰器或直接 register() 接入，零修改分发链
- 未命中任何命令时返回 False（不吞消息），由调用方决定后续处理
"""
import json

from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from app.permission import permission_service
from app.permission.constants import LEVEL_SYSTEM, LEVEL_OWNER, LEVEL_ADMIN, LEVEL_NONE
from .model import Command, CommandHandler

# 权限级别名称（帮助菜单展示）
LEVEL_NAMES = {
    LEVEL_SYSTEM: "系统管理员",
    LEVEL_OWNER: "群主",
    LEVEL_ADMIN: "群管理员",
    LEVEL_NONE: "所有用户",
}


class CommandRegistry:
    """命令注册与分发单例"""

    def __init__(self):
        self.logger = Logger("command_registry")
        self._commands: dict[str, Command] = {}  # name -> Command
        self._aliases: dict[str, Command] = {}    # alias -> Command
        # 注册内建 help（延迟到 __init__ 之后由 bootstrap 注册，避免循环依赖）

    # ---------- 注册 ----------

    def register(self, cmd: Command) -> bool:
        """注册命令；发现冲突时告警并跳过（不覆盖已有命令）"""
        for key in [cmd.name] + list(cmd.aliases):
            existing = self._commands.get(key) or self._aliases.get(key)
            if existing is not None:
                self.logger.warning(
                    f"命令冲突: '{key}' 已被 [{existing.app_name}] {existing.name} 注册，"
                    f"跳过 [{cmd.app_name}] {cmd.name} 的注册"
                )
                return False
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._aliases[alias] = cmd
        self.logger.debug(f"已注册命令 [{cmd.app_name}] {cmd.name} (别名: {cmd.aliases})")
        return True

    # ---------- 匹配 ----------

    def match(self, raw_message: str):
        """按首词匹配命令（支持多行命令，如 subscribe_group 格式）"""
        if not raw_message:
            return None
        first_line = raw_message.strip().splitlines()[0].strip()
        first_word = first_line.split(" ", 1)[0]
        cmd = self._commands.get(first_word)
        if cmd is not None:
            return cmd
        return self._aliases.get(first_word)

    # ---------- 分发 ----------

    async def dispatch(self, websocket, message) -> bool:
        """
        统一分发：匹配 → 鉴权 → handler → 回复。
        返回 True 表示已处理（含权限不足），False 表示未命中任何命令。
        """
        raw = str(message.get("raw_message", ""))
        cmd = self.match(raw)
        if cmd is None:
            return False

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))

        # 统一鉴权（required_level=LEVEL_NONE 表示无需权限）
        if cmd.required_level < LEVEL_NONE:
            if not permission_service.check_user_permission(group_id, user_id, cmd.required_level):
                need = LEVEL_NAMES.get(cmd.required_level, str(cmd.required_level))
                await self._reply(websocket, group_id,
                                  f"⚠️ 权限不足：命令 {cmd.name} 需要『{need}』权限")
                return True

        try:
            judge, reply = await cmd.handler(websocket, message)
        except Exception as e:
            self.logger.error(f"命令 {cmd.name} 执行异常: {e}")
            import traceback
            traceback.print_exc()
            await self._reply(websocket, group_id, f"❌ 命令 {cmd.name} 执行出错，请查看日志")
            return True

        if reply:
            await self._reply(websocket, group_id, reply)
        return True

    # ---------- 帮助 ----------

    def help_text(self, group_id, user_id, target: str = "") -> str:
        """
        生成帮助菜单：
        - 无 target：按 app 分组列出调用者有权限的命令
        - 有 target：显示指定命令/子命令的详细用法
        """
        if target:
            return self._help_detail(group_id, user_id, target)

        lines = ["📋 命令菜单\n"]
        grouped: dict[str, list[Command]] = {}
        for cmd in self._commands.values():
            if cmd.name == "/help":
                continue
            if not self._can_see(group_id, user_id, cmd):
                continue
            grouped.setdefault(cmd.app_name or "其他", []).append(cmd)

        for app_name, cmds in grouped.items():
            lines.append(f"🔹 {app_name}")
            for cmd in cmds:
                lines.append(self._format_cmd_line(cmd))
            lines.append("")

        if len(lines) == 1:
            lines.append("暂无可用命令，请联系管理员开通权限")
        lines.append("💡 输入 /help <命令名> 查看命令详情")
        return "\n".join(lines)

    def _help_detail(self, group_id, user_id, target: str) -> str:
        cmd = self._commands.get(target)
        if cmd is None:
            cmd = self._aliases.get(target)
        if cmd is None:
            return f"未找到命令: {target}（可用 /help 查看全部命令）"
        if not self._can_see(group_id, user_id, cmd):
            return f"无权查看命令 {target} 的详情"

        lines = [
            f"📌 {cmd.name}" + (f"（别名: {' / '.join(cmd.aliases)}）" if cmd.aliases else ""),
            f"📝 {cmd.description}",
            f"🔑 需要权限: {LEVEL_NAMES.get(cmd.required_level, cmd.required_level)}",
        ]
        if cmd.usage:
            lines.append(f"🔧 用法: {cmd.usage}")
        if cmd.sub_commands:
            lines.append("📂 子命令:")
            for sub, desc in cmd.sub_commands.items():
                lines.append(f"   · {cmd.name} {sub} - {desc}")
        return "\n".join(lines)

    def _can_see(self, group_id, user_id, cmd: Command) -> bool:
        """调用者是否能在帮助中看到该命令"""
        if cmd.required_level >= LEVEL_NONE:
            return True
        return permission_service.check_user_permission(group_id, user_id, cmd.required_level)

    @staticmethod
    def _format_cmd_line(cmd: Command) -> str:
        name = cmd.name
        perm = f"（{LEVEL_NAMES.get(cmd.required_level, '')}）" if cmd.required_level < LEVEL_NONE else ""
        if cmd.sub_commands:
            subs = " / ".join(f"{name} {s}" for s in cmd.sub_commands)
            return f"  {subs} - {cmd.description}{perm}"
        usage = f" {cmd.usage}" if cmd.usage else ""
        return f"  {name}{usage} - {cmd.description}{perm}"

    # ---------- 内部 ----------

    @staticmethod
    async def _reply(websocket, group_id, text: str) -> None:
        try:
            await QQAPI_list(websocket).send_group_message(group_id, text)
        except Exception as e:
            Logger("command_registry").error(f"发送命令回复失败: {e}")


# 全局单例
registry = CommandRegistry()
