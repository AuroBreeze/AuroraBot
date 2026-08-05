"""
命令注册中心（app/core/commands/registry.py）

职责：
- register: 注册命令，检测同名/别名/前缀冲突与格式问题（告警，不覆盖）
- dispatch: 首词匹配命令 → 统一权限校验 → 调用 handler → 统一发送回复
- help_text: 按调用者权限过滤、按 app 分组的帮助菜单；支持查看单个命令详情
- audit/summary: 命令健康检查（冲突、格式、统计），启动时输出报告

设计原则：
- 其他 app 通过装饰器或直接 register() 接入，零修改分发链
- 未命中任何命令时返回 False（不吞消息），由调用方决定后续处理
"""

from api.Logger_owner import Logger
from app.core.permission import permission_service
from app.core.permission.constants import (
    LEVEL_GROUP_PRIVILEGED, LEVEL_SYSTEM, LEVEL_OWNER, LEVEL_ADMIN, LEVEL_NONE,
)
from .model import Command, CommandHandler

# 权限级别名称（帮助菜单展示）
LEVEL_NAMES = {
    LEVEL_GROUP_PRIVILEGED: "系统管理员/本群管理权限",
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
        self._rejected: list[dict] = []           # 注册被拒的记录（冲突/格式问题）

    # ---------- 注册 ----------

    def unregister(self, name: str) -> bool:
        """移除单条命令及其全部别名（热更新专用；不存在的命令返回 False）"""
        cmd = self._commands.get(name)
        if cmd is None:
            return False
        for alias in cmd.aliases:
            self._aliases.pop(alias, None)
        del self._commands[name]
        self.logger.info(f"已注销命令 [{cmd.app_name}] {cmd.name}")
        return True

    def unregister_by_app(self, app_name: str) -> list[str]:
        """移除某个 app 注册的全部命令（含别名），返回被移除的命令名列表"""
        removed = []
        for name in list(self._commands):
            if self._commands[name].app_name == app_name:
                removed.append(name)
                self.unregister(name)
        # 清理该 app 的历史冲突记录（热更新后重新注册不应再报旧冲突）
        self._rejected = [r for r in self._rejected if r["app"] != app_name]
        return removed

    def snapshot(self, app_name: str) -> list:
        """快照某 app 已注册的命令（热更新失败回滚用）"""
        return [cmd for cmd in self._commands.values() if cmd.app_name == app_name]

    def restore(self, app_name: str, cmds: list) -> None:
        """重新注册快照命令（热更新失败回滚）"""
        for cmd in cmds:
            self.register(cmd)
        if cmds:
            self.logger.info(f"已恢复 {len(cmds)} 条命令 [{app_name}]")

    def register(self, cmd: Command) -> bool:
        """注册命令：先做格式校验，再做同名/别名冲突检测；冲突不覆盖、记录在案"""
        # 中文命令名自动纳入别名（中文操作与英文一致）
        if cmd.cn_name and cmd.cn_name not in cmd.aliases:
            cmd.aliases.append(cmd.cn_name)
        # 格式校验
        problems = self._validate(cmd)
        if problems:
            reason = "; ".join(problems)
            self.logger.warning(f"命令注册被拒 [{cmd.app_name}] {cmd.name}: {reason}")
            self._rejected.append({"app": cmd.app_name, "name": cmd.name, "reason": reason})
            return False

        # 同名/别名冲突检测（拒绝）
        for key in [cmd.name] + list(cmd.aliases):
            existing = self._commands.get(key) or self._aliases.get(key)
            if existing is not None:
                reason = f"'{key}' 已被 [{existing.app_name}] {existing.name} 占用"
                self.logger.warning(
                    f"命令冲突: {reason}，跳过 [{cmd.app_name}] {cmd.name} 的注册"
                )
                self._rejected.append({"app": cmd.app_name, "name": cmd.name, "reason": reason})
                return False

        # 前缀重叠检测（仅告警，不拒绝：首词精确匹配不受影响，但易造成混淆）
        self._check_prefix_conflicts(cmd)

        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._aliases[alias] = cmd
        self.logger.debug(f"已注册命令 [{cmd.app_name}] {cmd.name} (别名: {cmd.aliases})")
        return True

    @staticmethod
    def _validate(cmd: Command) -> list[str]:
        """命令定义格式校验，返回问题列表（空 = 无问题）"""
        problems = []
        if not cmd.name or not cmd.name.strip():
            problems.append("命令名不能为空")
        elif " " in cmd.name.strip():
            problems.append(f"命令名不能含空格: '{cmd.name}'")
        if not callable(cmd.handler):
            problems.append("handler 必须可调用")
        if not (LEVEL_GROUP_PRIVILEGED <= cmd.required_level <= LEVEL_NONE):
            problems.append(f"required_level 非法: {cmd.required_level}（应为 {LEVEL_GROUP_PRIVILEGED}-{LEVEL_NONE}）")
        for sub, desc in (cmd.sub_commands or {}).items():
            if not isinstance(desc, str) or not desc.strip():
                problems.append(f"子命令 '{sub}' 缺少说明")
        return problems

    def _check_prefix_conflicts(self, cmd: Command) -> None:
        """检测新命令与已注册命令的前缀重叠（首词互为前缀，仅告警）"""
        new_keys = [cmd.name] + list(cmd.aliases)
        for other in self._commands.values():
            other_keys = [other.name] + list(other.aliases)
            for nk in new_keys:
                for ok in other_keys:
                    if nk == ok:
                        continue
                    if nk.startswith(ok) or ok.startswith(nk):
                        self.logger.warning(
                            f"前缀重叠: 新命令 '{nk}' 与已有命令 '{ok}'"
                            f"（[{other.app_name}] {other.name}），首词虽精确匹配但易混淆"
                        )

    # ---------- 审计 ----------

    def audit(self) -> dict:
        """命令健康检查：统计 + 被拒冲突 + 当前前缀重叠"""
        by_app: dict[str, int] = {}
        for cmd in self._commands.values():
            app = cmd.app_name or "其他"
            by_app[app] = by_app.get(app, 0) + 1

        # 重算已注册命令间的前缀重叠（区分跨 app 与同 app）
        prefix_conflicts: list[tuple[str, str, bool]] = []  # (cmdA, cmdB, is_cross_app)
        cmds = list(self._commands.values())
        for i, a in enumerate(cmds):
            keys_a = [a.name] + list(a.aliases)
            for b in cmds[i + 1:]:
                keys_b = [b.name] + list(b.aliases)
                for ka in keys_a:
                    for kb in keys_b:
                        if ka == kb:
                            continue
                        if ka.startswith(kb) or kb.startswith(ka):
                            prefix_conflicts.append((ka, kb, a.app_name != b.app_name))

        return {
            "total": len(self._commands),
            "aliases": len(self._aliases),
            "apps": by_app,
            "conflicts": list(self._rejected),
            "prefix_conflicts": prefix_conflicts,
        }

    def report_text(self) -> str:
        """人类可读的审计报告"""
        a = self.audit()
        lines = [
            f"命令注册中心审计: 共 {a['total']} 条命令 / {a['aliases']} 个别名 / {len(a['apps'])} 个 app",
        ]
        for app, n in sorted(a["apps"].items()):
            lines.append(f"  [{app}] {n} 条")
        if a["conflicts"]:
            lines.append(f"注册被拒 {len(a['conflicts'])} 条冲突:")
            for c in a["conflicts"]:
                lines.append(f"  [{c['app']}] {c['name']}: {c['reason']}")
        else:
            lines.append("无注册冲突")
        if a["prefix_conflicts"]:
            cross = [p for p in a["prefix_conflicts"] if p[2]]
            same = [p for p in a["prefix_conflicts"] if not p[2]]
            if cross:
                lines.append(f"跨 app 前缀冲突 {len(cross)} 组（易混淆，建议改名）:")
                for ka, kb, _ in cross:
                    lines.append(f"  '{ka}' 与 '{kb}'")
            if same:
                lines.append(f"ℹ同 app 前缀重叠 {len(same)} 组（通常为关联命令，仅供参考）:")
                for ka, kb, _ in same:
                    lines.append(f"  '{ka}' 与 '{kb}'")
        return "\n".join(lines)

    def summary(self) -> None:
        """启动时输出审计报告（日志）"""
        self.logger.info(f"\n{self.report_text()}")

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
        if cmd.required_level == LEVEL_GROUP_PRIVILEGED:
            if not await self._check_group_privileged(group_id, user_id):
                await self._reply(websocket, group_id,
                                  f"权限不足：命令 {cmd.name} 需要『{LEVEL_NAMES.get(cmd.required_level)}』权限")
                return True
        elif cmd.required_level < LEVEL_NONE:
            if not permission_service.check_user_permission(group_id, user_id, cmd.required_level):
                need = LEVEL_NAMES.get(cmd.required_level, str(cmd.required_level))
                await self._reply(websocket, group_id,
                                  f"权限不足：命令 {cmd.name} 需要『{need}』权限")
                return True

        try:
            judge, reply = await cmd.handler(websocket, message)
        except Exception as e:
            self.logger.error(f"命令 {cmd.name} 执行异常: {e}", exc_info=True)
            await self._reply(websocket, group_id, f"命令 {cmd.name} 执行出错，请查看日志")
            return True

        if reply:
            await self._reply(websocket, group_id, reply)
        return True

    async def _check_group_privileged(self, group_id, user_id) -> bool:
        """LEVEL_GROUP_PRIVILEGED 鉴权：系统管理员 或 本群管理权限者
        （Lssuing 2 级 或 本群 role=owner/admin 的真实群管）"""
        if permission_service.is_admin(user_id):
            return True
        if permission_service.check_user_permission(group_id, user_id, 2):
            return True
        try:
            from app.core.runtime import get_api
            api = get_api()
            if api is None:
                return False
            members = await api.get_group_member_list(group_id)
            return any(str(m.get("user_id")) == user_id and m.get("role") in ("owner", "admin")
                       for m in members)
        except Exception:
            return False

    # ---------- 帮助 ----------

    def help_text(self, group_id, user_id, target: str = "") -> str:
        """
        生成帮助菜单：
        - 无 target：按 app 分组列出调用者有权限的命令
        - 有 target：显示指定命令/子命令的详细用法
        """
        if target:
            return self._help_detail(group_id, user_id, target)

        lines = [f"命令菜单（{'管理员' if self._is_privileged(group_id, user_id) else '成员'}模式）\n"]
        grouped: dict[str, list[Command]] = {}
        is_privileged = self._is_privileged(group_id, user_id)
        for cmd in self._commands.values():
            if cmd.name == "/help":
                continue
            # 权限者看全部命令；非权限者只看自己有权限的命令
            if not is_privileged and not self._can_see(group_id, user_id, cmd):
                continue
            grouped.setdefault(cmd.app_name or "其他", []).append(cmd)

        for app_name, cmds in grouped.items():
            lines.append(f"{app_name}")
            # 组内排序：权限级别（1=管理员最高）→ 命令名
            for cmd in sorted(cmds, key=lambda c: (c.required_level, c.name)):
                lines.append(self._format_cmd_line(cmd))
            lines.append("")

        if len(lines) == 1:
            lines.append("暂无可用命令，请联系管理员开通权限")
        if not is_privileged:
            lines.append("提示：管理命令（订阅/踢人/刷新/配置等）需要群管理权限")
        lines.append("输入 /help <命令名> 查看命令详情")
        return "\n".join(lines)

    def menu_text(self, group_id, user_id) -> str:
        """中文命令菜单：按 app 分组列出调用者有权限的命令（显示中文名，与英文功能一致）"""
        lines = [f"菜单（{'管理员' if self._is_privileged(group_id, user_id) else '成员'}）\n"]
        grouped: dict[str, list[Command]] = {}
        is_privileged = self._is_privileged(group_id, user_id)
        for cmd in self._commands.values():
            if cmd.name in ("/help", "/menu"):
                continue
            if not is_privileged and not self._can_see(group_id, user_id, cmd):
                continue
            grouped.setdefault(cmd.app_name or "其他", []).append(cmd)

        for app_name, cmds in grouped.items():
            lines.append(f"{app_name}")
            for cmd in sorted(cmds, key=lambda c: (c.required_level, c.name)):
                cn = cmd.cn_name or cmd.name
                lines.append(f"  {cn} - {cmd.description}")
            lines.append("")

        if len(lines) == 1:
            lines.append("暂无可用命令，请联系管理员开通权限")
        lines.append("提示：中文命令与英文命令功能一致（如 /踢人 同 /kick）")
        return "\n".join(lines)

    def _is_privileged(self, group_id, user_id) -> bool:
        """是否为群管理权限者（系统管理员或 Lssuing 2 级及以上）"""
        try:
            if permission_service.is_admin(user_id):
                return True
        except AttributeError:
            pass
        try:
            return permission_service.check_user_permission(group_id, user_id, 2)
        except Exception:
            return False

    def _help_detail(self, group_id, user_id, target: str) -> str:
        cmd = self._commands.get(target)
        if cmd is None:
            cmd = self._aliases.get(target)
        if cmd is None:
            return f"未找到命令: {target}（可用 /help 查看全部命令）"
        if not self._can_see(group_id, user_id, cmd):
            return f"无权查看命令 {target} 的详情"

        lines = [
            f"{cmd.name}" + (f"（别名: {' / '.join(cmd.aliases)}）" if cmd.aliases else ""),
            f"{cmd.description}",
            f"需要权限: {LEVEL_NAMES.get(cmd.required_level, cmd.required_level)}",
        ]
        if cmd.usage:
            lines.append(f"用法: {cmd.usage}")
        if cmd.detail:
            lines.append("详细说明:")
            for ln in cmd.detail.splitlines():
                lines.append(f"   {ln}")
        if cmd.example:
            lines.append("示例:")
            for ln in cmd.example.splitlines():
                lines.append(f"   {ln}")
        if cmd.sub_commands:
            lines.append("📂 子命令:")
            for sub, desc in cmd.sub_commands.items():
                lines.append(f"   · {cmd.name} {sub} - {desc}")
        return "\n".join(lines)

    def _can_see(self, group_id, user_id, cmd: Command) -> bool:
        """调用者是否能在帮助中看到该命令"""
        if cmd.required_level == LEVEL_GROUP_PRIVILEGED:
            return self._is_privileged(group_id, user_id)  # 同步判定（不含 role API 查询）
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
        # 多行用法（如完整版 subscribe_group）在菜单只显示第一行
        usage = cmd.usage.splitlines()[0] if cmd.usage else ""
        cmd_part = f"{name} {usage}".strip()
        return f"  {cmd_part:<30}- {cmd.description}{perm}"

    # ---------- 内部 ----------

    @staticmethod
    async def _reply(websocket, group_id, text: str) -> None:
        # 统一走运行时 API 实例（不得新建实例，否则 echo 注册表不共享导致响应投递失败）
        from app.core.runtime import get_api
        api = get_api()
        if api is None:
            Logger("command_registry").warning("命令回复失败：API 不可用")
            return
        try:
            await api.send_group_message(group_id, text)
        except Exception as e:
            Logger("command_registry").error(f"发送命令回复失败: {e}")


# 全局单例
registry = CommandRegistry()
