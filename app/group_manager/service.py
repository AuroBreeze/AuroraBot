"""
群管业务层（app/group_manager/service.py）

组合底层原语实现：
- 入群引导：欢迎语 + 踢人规则 + 链接 + 段位询问（MemberStore.extras 状态机）
- 观察期：入群 N 分钟未发言 → 踢出（TaskScheduler + set_group_kick_member）
- 活跃记录：MESSAGE 事件更新 last_active（MemberStore）
- 自动同意入群：GROUP_REQUEST 事件按策略同意（set_group_add_request）
"""
import re
from datetime import datetime

import pytz

from api.Logger_owner import Logger
from config.env import TIMEZONE
from app.core import member_store
from app.core.tasks import task_scheduler
from app.core.runtime import get_api
from . import config as gm_config


class GroupManagerService:
    """群管业务（进程内单例）"""

    def __init__(self):
        self.logger = Logger("group_manager")
        self.store = member_store.member_store
        self.bj_tz = pytz.timezone(TIMEZONE)

    def _now_str(self) -> str:
        return datetime.now(self.bj_tz).strftime("%Y-%m-%d %H:%M:%S")

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

        # 欢迎 + 规则 + 链接 + 段位询问（要求回复此条消息登记）
        msg = self._welcome_text(user_id, observe_minutes)
        msg_id = await api.send_group_message(group_id, msg)

        # 段位询问状态机：记录欢迎消息 id，用户回复该消息才登记
        extras = self.store.get_extras(group_id, user_id)
        extras["flow"] = "awaiting_tier"
        extras["welcome_msg_id"] = str(msg_id) if msg_id is not None else ""
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
        """
        用户回复欢迎消息登记段位（MESSAGE 事件）：
        仅当消息带 reply 段且 reply id == 欢迎消息 id 时登记，否则忽略。
        """
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

        # 必须回复群管发送的欢迎消息
        reply_id = self.get_reply_id(event)
        if not reply_id or reply_id != extras.get("welcome_msg_id"):
            return

        # 剥离回复/@ 等 CQ 段，只保留纯文本作为段位
        clean = re.sub(r"\[CQ:[^\]]+\]", "", raw).strip()
        if not clean:
            return

        extras["tier"] = clean
        extras["tier_time"] = self._now_str()  # 记录段位登记时间
        extras["flow"] = ""  # 流程完成
        self.store.set_extras(group_id, user_id, extras)
        confirm = gm_config.get()["tier_confirm"].format(tier=clean)
        # 用 at 段发送（文本里的 CQ 码不会解析）
        await api.send_at_group_message(group_id, user_id, confirm)

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

    # ---------- 存量成员批量补记录 ----------

    async def backfill_group(self, group_id) -> tuple[int, int]:
        """
        对单个群批量补记录：拉取真实群成员列表，补齐缺失的 MemberStore 记录。
        已存在的记录（含 join_time/extras）不被覆盖；完成后标记该群已处理。
        :return: (新增数量, 群成员总数)
        """
        api = get_api()
        if api is None:
            return 0, 0
        members = await api.get_group_member_list(group_id)
        added = 0
        for member in members:
            user_id = str(member.get("user_id") or "")
            if user_id and self.store.ensure_member(group_id, user_id):
                added += 1
        self.store.mark_backfilled(group_id)
        self.logger.info(f"存量成员补记录 群:{group_id} 新增:{added}/{len(members)}")
        return added, len(members)

    async def backfill_all(self) -> str:
        """
        对所有已授权群批量补记录（仅授权群；未授权群跳过）。
        返回结果描述。
        """
        api = get_api()
        if api is None:
            return "⚠️ API 不可用，无法补记录"
        from app.permission import permission_service

        lines = []
        total_added = 0
        for group_id in await api.get_group_list():
            if not permission_service.check_group_authorized(group_id):
                lines.append(f"群 {group_id}: 未授权，跳过")
                continue
            added, total = await self.backfill_group(group_id)
            total_added += added
            lines.append(f"群 {group_id}: 补记录 {added}/{total}")
        lines.insert(0, f"✅ 存量成员补记录完成，共新增 {total_added} 条")
        return "\n".join(lines)

    async def auto_backfill_pending(self) -> None:
        """
        自动补记录（后台周期任务）：对未标记过的已授权群补一次记录。
        幂等：已标记（处理过）的群跳过；未连接/无 API 时静默跳过。
        """
        api = get_api()
        if api is None:
            return
        from app.permission import permission_service

        for group_id in await api.get_group_list():
            if not permission_service.check_group_authorized(group_id):
                continue
            if self.store.is_backfilled(group_id):
                continue
            added, total = await self.backfill_group(group_id)
            self.logger.info(f"自动补记录 群:{group_id} 新增:{added}/{total}")

    # ---------- 批量成员信息 ----------

    @staticmethod
    def _fmt_time(ts) -> str:
        """时间缩写 MM-DD HH:MM；空值 → '-'"""
        if not ts:
            return "-"
        try:
            return ts[5:16]  # "2026-01-05 08:00:00" -> "01-05 08:00"
        except (IndexError, TypeError):
            return str(ts)

    def list_members(self, group_id, page: int = 1, page_size: int = 20) -> str:
        """
        批量显示群成员信息：加入时间 / 最后活跃 / 游戏段位 / 段位登记时间。
        分页输出；无记录时提示先补记录。
        """
        members = self.store.get_members(group_id)
        if not members:
            return "本群暂无成员记录（可先执行 /backfill 补记录）"

        total = len(members)
        total_pages = max(1, -(-total // page_size))
        if page < 1 or page > total_pages:
            return f"页码越界：共 {total_pages} 页（/members 1-{total_pages}）"

        start = (page - 1) * page_size
        rows = members[start:start + page_size]
        lines = [f"📋 群成员档案（本群 {total} 人，第 {page}/{total_pages} 页）"]
        for i, m in enumerate(rows, start=start + 1):
            extras = m["extras"]
            tier = extras.get("tier") or "-"
            tier_time = self._fmt_time(extras.get("tier_time"))
            lines.append(
                f"{i}. {m['user_id']} "
                f"加入:{self._fmt_time(m['join_time'])} "
                f"活跃:{self._fmt_time(m['last_active'])} "
                f"段位:{tier} 登记:{tier_time}"
            )
        if total_pages > 1:
            nxt = page + 1 if page < total_pages else 1
            lines.append(f"💡 /members {nxt} 查看下一页")
        return "\n".join(lines)

    # ---------- 工具 ----------

    @staticmethod
    def get_reply_id(event) -> str:
        """
        提取消息引用的回复消息 id（回复群管欢迎消息用）：
        优先 message 数组的 reply 段，兜底 raw_message 中的 CQ:reply 码
        """
        for seg in (event.data.get("message") or []):
            if seg.get("type") == "reply":
                return str(seg.get("data", {}).get("id", ""))
        m = re.search(r"\[CQ:reply,id=(-?\d+)\]", str(event.raw_message or ""))
        return m.group(1) if m else ""

    @staticmethod
    def parse_at(raw: str) -> str:
        """从 raw_message 提取 @ 的 qq；无 @ 返回 ''"""
        m = re.search(r"\[CQ:at,qq=(\d+)\]", raw or "")
        return m.group(1) if m else ""


# 进程内单例
group_manager_service = GroupManagerService()
