"""
群管业务层（app/group_manager/service.py）

组合底层原语实现：
- 入群引导：欢迎语 + 踢人规则 + 链接 + 段位询问（MemberStore.extras 状态机）
- 观察期：入群 N 分钟未发言 → 踢出（TaskScheduler + set_group_kick_member）
- 活跃记录：MESSAGE 事件更新 last_active（MemberStore）
- 自动同意入群：GROUP_REQUEST 事件按策略同意（set_group_add_request）
"""
import re

from api.Logger_owner import Logger
from app.core import member_store
from app.core.tasks import task_scheduler
from app.core.runtime import get_api
from . import config as gm_config


class GroupManagerService:
    """群管业务（进程内单例）"""

    def __init__(self):
        self.logger = Logger("group_manager")
        self.store = member_store.member_store

    # ---------- 入群引导 ----------

    async def on_member_join(self, event) -> None:
        """入群完成（GROUP_INCREASE）：记录成员 + 欢迎/规则/链接 + 段位询问 + 观察期"""
        if not gm_config.get_bool("enabled", True):
            return
        api = get_api()
        if api is None:
            self.logger.warning("入群引导：API 不可用，跳过")
            return
        group_id = str(event.group_id)
        user_id = event.user_id
        if not group_id or not user_id:
            return

        self.store.record_join(group_id, user_id)

        # 观察期任务：N 分钟未发言踢出
        observe_minutes = gm_config.get_int("observe_minutes", 10)
        task_scheduler.schedule(
            f"observe_{group_id}_{user_id}",
            observe_minutes * 60,
            self._check_observation,
            group_id, user_id,
        )

        # 欢迎 + 规则 + 链接 + 段位询问
        msg = self._welcome_text(user_id, observe_minutes)
        await api.send_group_message(group_id, msg)

        # 段位询问状态机：置 awaiting_tier
        extras = self.store.get_extras(group_id, user_id)
        extras["flow"] = "awaiting_tier"
        self.store.set_extras(group_id, user_id, extras)

    def _welcome_text(self, user_id: str, minutes: int) -> str:
        cfg = gm_config.get()
        rules = cfg["rules_msg"].format(minutes=minutes)
        return cfg["welcome_msg"].format(
            user=user_id, rules=rules, link=cfg["link"], question=cfg["tier_question"]
        )

    # ---------- 观察期检查 ----------

    async def _check_observation(self, group_id: str, user_id: str) -> None:
        """观察期到：未发言（last_active 为空）→ 踢出"""
        api = get_api()
        if api is None:
            self.logger.warning("观察期检查：API 不可用，跳过")
            return
        member = self.store.get_member(group_id, user_id)
        if member is None:
            return  # 已退群/被清理
        if member["last_active"]:
            self.logger.info(f"成员 {user_id} 观察期内已发言，跳过踢出")
            return
        ok = await api.set_group_kick_member(group_id, user_id)
        self.logger.info(f"观察期未发言踢出 群:{group_id} 用户:{user_id} 结果:{ok}")

    # ---------- 活跃记录 ----------

    def record_active(self, group_id, user_id) -> None:
        """更新最后发言时间（MESSAGE 事件高频调用）"""
        if group_id and user_id:
            self.store.record_message(group_id, user_id)

    # ---------- 段位状态机 ----------

    async def handle_tier_reply(self, event) -> None:
        """用户回复段位（MESSAGE 事件）：flow==awaiting_tier → 登记并确认"""
        api = get_api()
        if api is None:
            return
        group_id = str(event.group_id)
        user_id = event.user_id
        raw = str(event.raw_message or "").strip()
        if not group_id or not user_id or not raw:
            return

        extras = self.store.get_extras(group_id, user_id)
        if extras.get("flow") != "awaiting_tier":
            return

        extras["tier"] = raw
        extras["flow"] = ""  # 流程完成
        self.store.set_extras(group_id, user_id, extras)
        confirm = gm_config.get()["tier_confirm"].format(tier=raw)
        await api.send_group_message(group_id, f"[CQ:at,qq={user_id}] {confirm}")

    # ---------- 自动同意入群 ----------

    async def handle_group_request(self, event) -> None:
        """入群申请（GROUP_REQUEST）：按策略自动同意"""
        if not gm_config.get_bool("auto_approve", True):
            return
        if event.data.get("sub_type") != "add":
            return  # 仅自动处理主动申请；邀请留给管理员
        group_id = str(event.group_id)
        flag = event.data.get("flag")
        api = get_api()
        if api is None or not flag or not group_id:
            return

        scope = gm_config.get_str("auto_approve_scope", "authorized")
        if scope == "authorized":
            from app.permission import permission_service
            if not permission_service.check_group_authorized(group_id):
                self.logger.info(f"群 {group_id} 未授权，跳过自动同意")
                return

        ok = await api.set_group_add_request(flag, True)
        self.logger.info(f"自动同意入群 群:{group_id} 用户:{event.user_id} 结果:{ok}")

    # ---------- 查询 ----------

    async def query_member(self, group_id, user_id) -> str:
        """
        成员档案：入群时间 / 最后活跃 / 游戏段位。
        无本地记录时调用 API 验证真实群成员身份：
        - 是成员 → 补记录并提示"暂无活跃/段位记录"
        - 非成员 → "不是本群成员"
        - API 不可用 → 提示无法验证
        """
        member = self.store.get_member(group_id, user_id)
        if member is not None:
            lines = [f"用户 {user_id}"]
            lines.append(f"入群时间: {member['join_time'] or '未知'}")
            lines.append(f"最后活跃: {member['last_active'] or '未发言'}")
            lines.append(f"游戏段位: {member['extras'].get('tier') or '未登记'}")
            return "\n".join(lines)

        # 无本地记录：验证是否真实群成员（存量成员未经过入群流程）
        api = get_api()
        if api is None:
            return f"用户 {user_id} 暂无记录（API 不可用，无法验证成员身份）"

        info = await api.get_group_member_info(group_id, user_id)
        if info:
            # 确认是群成员：补记录（后续活跃统计/段位流程可正常进行）
            self.store.record_join(group_id, user_id)
            self.logger.info(f"存量群成员补记录 群:{group_id} 用户:{user_id}")
            return f"用户 {user_id} 是本群成员，但暂无活跃/段位记录（存量成员，未经过入群登记流程）"

        return f"用户 {user_id} 不是本群成员"

    # ---------- 工具 ----------

    @staticmethod
    def parse_at(raw: str) -> str:
        """从 raw_message 提取 @ 的 qq；无 @ 返回 ''"""
        m = re.search(r"\[CQ:at,qq=(\d+)\]", raw or "")
        return m.group(1) if m else ""


# 进程内单例
group_manager_service = GroupManagerService()
