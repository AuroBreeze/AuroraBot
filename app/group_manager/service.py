"""
群管业务层（app/group_manager/service.py）

组合底层原语实现：
- 入群引导：欢迎语 + 踢人规则 + 链接 + 段位询问（MemberStore.extras 状态机）
- 观察期：入群 N 分钟未发言 → 踢出（TaskScheduler + set_group_kick_member）
- 活跃记录：MESSAGE 事件更新 last_active（MemberStore）
- 自动同意入群：GROUP_REQUEST 事件按策略同意（set_group_add_request）
"""
import re
from datetime import datetime, timedelta

from api.Logger_owner import Logger
from app.core import member_store, timeutil
from app.core.tasks import task_scheduler
from app.core.runtime import get_api, get_self_id
from . import config as gm_config


class GroupManagerService:
    """群管业务（进程内单例）"""

    def __init__(self):
        self.logger = Logger("group_manager")
        self.store = member_store.member_store
        # 最近一次 /inactive 列表缓存（group_id -> 完整降序 user_id 列表），供 /kick 数字序号
        self._last_inactive: dict[str, list] = {}

    def _now_str(self) -> str:
        return timeutil.now_str()

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
        # 机器人自己入群：不引导、不观察期（避免 bot 被自己踢出）
        if user_id == get_self_id():
            self.logger.info(f"机器人自身入群 群:{group_id}，跳过引导流程")
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

        # 欢迎 + 规则 + 链接 + 段位询问（要求回复此条消息登记）；@ 新人，不显示纯数字
        msg = self._welcome_text(user_id, observe_minutes)
        msg_id = await api.send_group_message_array(group_id, [
            {"type": "at", "data": {"qq": user_id}},
            {"type": "text", "data": {"text": " "}},
            {"type": "text", "data": {"text": msg}},
        ])

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
        """观察期到：未发言（last_active 为空）→ 默认询问真实群主，确认后才踢"""
        api = get_api()
        if api is None:
            self.logger.warning("观察期检查：API 不可用，跳过")
            return
        # 绝不踢机器人自己（防御，双保险）
        if user_id == get_self_id():
            self.logger.info(f"跳过机器人自身 群:{group_id}，不踢出")
            return
        member = self.store.get_member(group_id, user_id)
        if member is None:
            return  # 已退群/被清理
        if member["last_active"]:
            self.logger.info(f"成员 {user_id} 观察期内已发言，跳过踢出")
            return
        # 未发言：开启"询问群主"时先征求真实群主确认（安全默认：不回复不踢）
        if gm_config.get_bool("observe_ask_owner", True):
            await self._ask_owner_before_kick(group_id, user_id)
            return
        ok = await api.set_group_kick_member(group_id, user_id)
        self.logger.info(f"观察期未发言踢出 群:{group_id} 用户:{user_id} 结果:{ok}")

    async def _ask_owner_before_kick(self, group_id: str, user_id: str) -> None:
        """观察期到期未发言：默认先只问群主；超时未回复再 @管理员/被授权用户；处理完毕即结束。"""
        api = get_api()
        if api is None:
            return
        extras = self.store.get_extras(group_id, user_id)
        today = timeutil.bj_now().strftime("%Y-%m-%d")
        timeout_s = gm_config.get_int("observe_owner_timeout", 30) * 60

        if extras.get("observe_pending") == "asking":
            if extras.get("observe_asked_date") != today:
                pass  # 隔日：允许重新询问
            elif extras.get("observe_phase") == "managers":
                return  # 已升级且今日已问，等待群管回复
            elif extras.get("observe_phase") == "owner":
                # 群主超时兜底（重启丢升级任务等场景）：直接升级到群管
                asked_dt = timeutil.parse_local(extras.get("observe_asked_time") or "")
                if asked_dt and (timeutil.bj_now() - asked_dt).total_seconds() >= timeout_s:
                    await self._ask_managers_phase(group_id, user_id, extras)
                return  # 未超时：等群主回复或升级任务触发
        try:
            members = await api.get_group_member_list(group_id)
        except Exception:
            self.logger.warning(f"观察期成员 {user_id} 未发言，查询群管失败，跳过（不踢）")
            return
        from app.core.permission import permission_service
        owner = next((str(m.get("user_id")) for m in members if m.get("role") == "owner"), None)
        if owner:
            # 阶段 1：只 @ 群主（同时 @ 新人指明对象）；超时未回复 → 升级任务
            minutes = gm_config.get_int("observe_minutes", 10)
            msg_id = await api.send_group_message_array(group_id, [
                {"type": "at", "data": {"qq": owner}},
                {"type": "at", "data": {"qq": user_id}},
                {"type": "text", "data": {
                    "text": f" ⚠️ 新人入群 {minutes} 分钟未发言，是否移出？\n"
                            f"同意：回复此消息 1\n拒绝：回复此消息 0",
                }},
            ])
            extras["observe_pending"] = "asking"
            extras["observe_phase"] = "owner"
            extras["observe_asked_date"] = today
            extras["observe_asked_time"] = timeutil.now_str()
            extras["observe_ask_msg_id"] = str(msg_id) if msg_id is not None else ""
            self.store.set_extras(group_id, user_id, extras)
            task_scheduler.schedule(
                f"observe_escalate_{group_id}_{user_id}", timeout_s,
                self._escalate_observe, group_id, user_id,
            )
            self.logger.info(f"观察期询问群主 群:{group_id} 成员:{user_id} 群主:{owner}（{timeout_s // 60} 分钟后升级群管）")
        else:
            # 无群主：直接问管理员/被授权用户
            await self._ask_managers_phase(group_id, user_id, extras)

    async def _ask_managers_phase(self, group_id: str, user_id: str, extras: dict) -> None:
        """阶段 2：优先 @ 在线的管理员/被授权用户（最近发言者），请他们确认（处理完毕即结束）"""
        api = get_api()
        if api is None:
            return
        members = await api.get_group_member_list(group_id)
        from app.core.permission import permission_service
        candidates, seen = [], set()
        for m in members:
            uid = str(m.get("user_id") or "")
            if not uid or uid in seen:
                continue
            role = m.get("role", "")
            # 阶段 2 不再 @ 群主：仅管理员与被授权用户
            if role == "admin" or permission_service.check_user_permission(group_id, uid, 2):
                seen.add(uid)
                member = self.store.get_member(group_id, uid)
                candidates.append((uid, timeutil.parse_local((member or {}).get("last_active") or "")))
        if not candidates:
            self.logger.warning(f"观察期成员 {user_id} 未发言但找不到群主/管理员/被授权用户，跳过（不踢）")
            return
        now = timeutil.bj_now()
        online_min = gm_config.get_int("observe_online_minutes", 10)
        at_most = max(1, gm_config.get_int("observe_escalate_at", 2))
        # 按最近发言排序（无发言记录的排最后）
        ranked = sorted(candidates, key=lambda c: (c[1] is None, -(c[1].timestamp() if c[1] else 0)))
        online = [uid for uid, dt in ranked
                  if dt is not None and 0 <= (now - dt).total_seconds() <= online_min * 60]
        targets = (online or [uid for uid, _ in ranked])[:at_most]
        minutes = gm_config.get_int("observe_minutes", 10)
        at_segs = [{"type": "at", "data": {"qq": m}} for m in targets]
        at_segs.append({"type": "at", "data": {"qq": user_id}})  # @ 新人指明对象
        at_segs.append({"type": "text", "data": {
            "text": f" ⚠️ 群主暂未处理，新人入群 {minutes} 分钟未发言，是否移出？\n"
                    f"同意：回复此消息 1\n拒绝：回复此消息 0",
        }})
        msg_id = await api.send_group_message_array(group_id, at_segs)
        extras["observe_pending"] = "asking"
        extras["observe_phase"] = "managers"
        extras["observe_asked_date"] = timeutil.bj_now().strftime("%Y-%m-%d")
        extras["observe_asked_time"] = timeutil.now_str()
        extras["observe_ask_msg_id"] = str(msg_id) if msg_id is not None else ""
        self.store.set_extras(group_id, user_id, extras)
        self.logger.info(f"观察期升级询问群管 群:{group_id} 成员:{user_id} 群管:{targets}")

    async def _escalate_observe(self, group_id: str, user_id: str) -> None:
        """群主超时未回复：升级到 @管理员/被授权用户"""
        extras = self.store.get_extras(group_id, user_id)
        if extras.get("observe_pending") != "asking" or extras.get("observe_phase") != "owner":
            return  # 已处理或已升级
        await self._ask_managers_phase(group_id, user_id, extras)

    async def handle_observe_reply(self, event) -> None:
        """群管回复观察期询问：回复该询问消息并输入 1（同意）/ 0（拒绝），精确处理对应成员。

        仅群主/管理员/被授权用户生效；不回复询问消息（无 reply id）时忽略，
        避免误把日常数字消息当成确认。
        """
        data = event.data
        group_id = str(event.group_id or "")
        if not group_id:
            return
        sender = data.get("sender") or {}
        sender_role = sender.get("role", "")
        sender_uid = str(data.get("user_id") or "")
        # 群管理权限者：群主/管理员（role）或 被授权用户（Lssuing 2 级+）
        from app.core.permission import permission_service
        if sender_role not in ("owner", "admin") and not permission_service.check_user_permission(group_id, sender_uid, 2):
            return  # 仅群主/管理员/被授权用户可确认
        raw = str(data.get("raw_message") or "").strip()
        # 提取消息纯文本（message 数组 text 段优先，兜底剔除 CQ 码后的 raw_message）
        segs = data.get("message") or []
        content = "".join((s.get("data") or {}).get("text", "") for s in segs if s.get("type") == "text")
        if not content:
            content = re.sub(r"\[CQ:[^\]]*\]", "", raw).strip()
        content = content.strip()
        if content not in ("1", "0"):
            return  # 仅接受纯 1 / 0（且必须回复询问消息）
        reply_id = self.get_reply_id(event)
        if not reply_id:
            return  # 未回复询问消息，忽略
        # 精确匹配：该询问消息对应的成员
        api = get_api()
        if api is None:
            return
        for member in self.store.get_members(group_id):
            extras = self.store.get_extras(group_id, member["user_id"])
            if extras.get("observe_pending") == "asking" and extras.get("observe_ask_msg_id") == reply_id:
                if content == "1":
                    ok = await api.set_group_kick_member(group_id, member["user_id"])
                    extras["observe_pending"] = "resolved"
                    self.logger.info(f"群管回复 1 同意移出 群:{group_id} 成员:{member['user_id']} 结果:{ok}")
                else:
                    extras["observe_pending"] = "rejected"
                    self.logger.info(f"群管回复 0 拒绝移出 群:{group_id} 成员:{member['user_id']}（保留）")
                self.store.set_extras(group_id, member["user_id"], extras)
                return

    # ---------- 活跃记录 ----------

    def record_active(self, group_id, user_id, nickname: str | None = None) -> None:
        """更新最后发言时间（MESSAGE 事件高频调用），顺带保存昵称"""
        if group_id and user_id:
            self.store.record_message(group_id, user_id, nickname)

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
            from app.core.permission import permission_service
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
        from app.core.permission import permission_service

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
        if not gm_config.get_bool("auto_backfill", True):
            return
        api = get_api()
        if api is None:
            return
        from app.core.permission import permission_service

        for group_id in await api.get_group_list():
            if not permission_service.check_group_authorized(group_id):
                continue
            if self.store.is_backfilled(group_id):
                continue
            added, total = await self.backfill_group(group_id)
            self.logger.info(f"自动补记录 群:{group_id} 新增:{added}/{total}")

    # ---------- API 活跃同步（get_group_member_info → sqlite） ----------

    async def sync_group_members_active(self, group_id: str) -> tuple[int, int]:
        """
        遍历群全部成员，逐个调 get_group_member_info：
        用 last_sent_time / join_time（Unix 秒）更新 sqlite 活跃与入群时间。
        返回 (更新成功数, 成员总数)。单成员查询失败不影响整体。
        """
        api = get_api()
        if api is None:
            return 0, 0
        try:
            members = await api.get_group_member_list(group_id)
        except Exception:
            return 0, 0
        updated, total = 0, 0
        for m in members:
            uid = str(m.get("user_id") or "")
            if not uid or uid == get_self_id():
                continue
            total += 1
            try:
                info = await api.get_group_member_info(group_id, uid)
            except Exception:
                continue  # 单成员查询失败不阻断
            last_dt = timeutil.from_ts(info.get("last_sent_time"))
            join_dt = timeutil.from_ts(info.get("join_time"))
            self.store.upsert_member(
                group_id, uid,
                timeutil.format_local(join_dt) if join_dt else None,
                timeutil.format_local(last_dt) if last_dt else None,
                nickname=str(info.get("nickname") or "") or None,
            )
            updated += 1
        return updated, total

    async def sync_all_groups_active(self, force: bool = False) -> str:
        """遍历全部已授权群同步成员活跃；force=True 时无视开关（手动强制刷新）"""
        if not force and not gm_config.get_bool("active_sync_enabled", True):
            return "活跃同步已关闭（active_sync_enabled=false），可用 /sync_active 强制刷新"
        api = get_api()
        if api is None:
            return "连接不可用，请稍后重试"
        from app.core.permission import permission_service
        lines = []
        for group_id in await api.get_group_list():
            if not permission_service.check_group_authorized(group_id):
                continue
            updated, total = await self.sync_group_members_active(group_id)
            lines.append(f"群 {group_id}: 更新 {updated}/{total}")
            self.logger.info(f"活跃同步 群:{group_id} 更新:{updated}/{total}")
        if not lines:
            return "没有已授权群可同步（先 /sub_group 授权）"
        return "✅ 活跃同步完成（last_sent_time/nickname 已刷新）\n" + "\n".join(lines)

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

    # ---------- 不活跃自动踢人 ----------

    async def scan_inactive_members(self) -> None:
        """
        定期扫描：群成员不活跃超期 → 踢出（后台周期任务）。
        - 超期判定：仅按 last_active（真实发言记录）判定；无发言记录（NULL）不参与，
          由入群观察期负责新成员，避免重置/补录后 join_time 兜底误踢老成员
        - 排除：bot 自己 / 群主与管理员（role）/ 有权限用户（Lssuing 2/3 级）
        - 踢前提醒：剩余天数 <= inactive_remind_days 时 @ 提醒（当天不重复）
        """
        if not gm_config.get_bool("inactive_kick_enabled", True):
            return
        api = get_api()
        if api is None:
            return
        from app.core.permission import permission_service

        days = gm_config.get_int("inactive_kick_days", 7)
        remind_days = gm_config.get_int("inactive_remind_days", 1)
        now = timeutil.bj_now()

        for group_id in await api.get_group_list():
            if not permission_service.check_group_authorized(group_id):
                continue
            # 一次拉取成员 role（群主/管理员排除），避免逐人查 API
            role_map = {str(m.get("user_id") or ""): m.get("role", "")
                        for m in await api.get_group_member_list(group_id)}

            for member in self.store.get_members(group_id):
                uid = member["user_id"]
                # 统一保护：机器人自己 / 非群成员（退群残留）/ 群主管理员 / 有权限用户
                if self._kick_reason(group_id, uid, role_map):
                    continue

                # 不活跃时长：仅真实发言记录；无发言记录跳过（防误踢）
                last = member["last_active"]
                if not last:
                    continue
                last_dt = timeutil.parse_local(last)
                if last_dt is None:
                    continue
                inactive = (now - last_dt).days

                if inactive >= days:
                    ok = await api.set_group_kick_member(group_id, uid)
                    self.logger.info(f"不活跃踢出 群:{group_id} 用户:{uid} 不活跃:{inactive}天 结果:{ok}")
                elif inactive >= days - remind_days:
                    await self._remind_inactive(group_id, uid, days, inactive)

    async def _remind_inactive(self, group_id: str, user_id: str, days: int, inactive: int) -> None:
        """踢前提醒（当天不重复）"""
        api = get_api()
        if api is None:
            return
        today = timeutil.bj_now().strftime("%Y-%m-%d")
        extras = self.store.get_extras(group_id, user_id)
        if extras.get("inactive_reminded") == today:
            return
        left = days - inactive
        msg = gm_config.get()["inactive_remind_msg"].format(days=inactive, left=left)
        await api.send_at_group_message(group_id, user_id, msg)
        extras["inactive_reminded"] = today
        self.store.set_extras(group_id, user_id, extras)
        self.logger.info(f"不活跃提醒 群:{group_id} 用户:{user_id} 剩余:{left}天")

    # ---------- 不活跃成员列表 / 批量踢人 ----------

    def _member_inactive_days(self, member: dict, now: datetime):
        """成员未活跃天数；仅按真实发言记录（last_active）；无记录/无法解析返回 None"""
        last = member.get("last_active")
        if not last:
            return None
        last_dt = timeutil.parse_local(last)
        if last_dt is None:
            return None
        return (now - last_dt).days

    def list_inactive_members(self, group_id: str, days: int, page: int = 0, page_size: int = 10) -> str:
        """列出本群不活跃成员：序号 + @ + 未活跃天数，按天数降序；page<=0 全部列出，>0 分页；缓存完整列表供 /kick 用"""
        days = max(1, days)
        now = timeutil.bj_now()
        rows = []
        for member in self.store.get_members(group_id):
            uid = member.get("user_id")
            if not uid or uid == get_self_id():
                continue
            inactive = self._member_inactive_days(member, now)
            if inactive is None or inactive < days:
                continue
            rows.append((uid, inactive))
        # 降序：未活跃天数多者在前，同天数按 QQ 号
        rows.sort(key=lambda r: (-r[1], r[0]))
        self._last_inactive[group_id] = [uid for uid, _ in rows]

        total = len(rows)
        if page and page > 0:
            # 显式页码 → 分页
            pages = max(1, -(-total // page_size))
            page = max(1, min(page, pages))
            shown = rows[(page - 1) * page_size: page * page_size]
            head = f"📋 本群不活跃成员（≥{days} 天，共 {total} 人，第 {page}/{pages} 页）"
            start_idx = (page - 1) * page_size + 1
        else:
            # 未指定页码 → 全部列出
            shown = rows
            head = f"📋 本群不活跃成员（≥{days} 天，共 {total} 人）"
            start_idx = 1
        lines = [head]
        for idx, (uid, inactive) in enumerate(shown, start_idx):
            lines.append(f"{idx}. [CQ:at,qq={uid}]  未活跃 {inactive} 天")
        if total:
            lines.append("💡 /kick 批量移出：/kick 1 3 @用户 QQ号（数字=本列表序号）")
        else:
            lines.append("✅ 没有不活跃成员")
        return "\n".join(lines)

    async def kick_members(self, group_id: str, operator_id: str, raw: str) -> str:
        """批量踢人：@用户 / QQ号 / 上次 /inactive 列表序号（可混合、空格分隔）"""
        parts = raw.split()
        if len(parts) < 2:
            return "用法：/kick @用户 QQ号 列表序号（可混合，空格分隔）"
        api = get_api()
        if api is None:
            return "连接不可用，请稍后重试"

        role_map = {str(m.get("user_id") or ""): m.get("role", "")
                    for m in await api.get_group_member_list(group_id)}
        cached = self._last_inactive.get(group_id, [])

        targets = []
        for p in parts[1:]:
            if p.startswith("[CQ:at"):
                uid = self.parse_at(p)
                if uid:
                    targets.append(uid)
            elif p.isdigit():
                n = int(p)
                if cached and 1 <= n <= len(cached):
                    targets.append(cached[n - 1])  # 上一步列表序号
                else:
                    targets.append(p)  # 按 QQ 号
        # 去重（保持顺序）
        seen, uniq = set(), []
        for t in targets:
            if t and t not in seen:
                seen.add(t)
                uniq.append(t)

        ok_list, skip = [], []
        for uid in uniq:
            reason = self._kick_reason(group_id, uid, role_map)
            if reason:
                skip.append(f"{uid}({reason})")
            elif await api.set_group_kick_member(group_id, uid):
                ok_list.append(uid)
            else:
                skip.append(f"{uid}(踢出失败)")

        if not ok_list and not skip:
            return "未识别到有效目标"
        text = f"✅ 已移出 {len(ok_list)} 人" + (
            "：" + " ".join(f"[CQ:at,qq={u}]" for u in ok_list) if ok_list else ""
        )
        if skip:
            text += f"\n⏭️ 跳过 {len(skip)} 人：" + "、".join(skip[:8]) + ("…" if len(skip) > 8 else "")
        return text

    # ---------- 工具 ----------

    def _kick_reason(self, group_id: str, uid: str, role_map: dict) -> str | None:
        """返回不可踢原因（None=可踢）：机器人自己 / 非群成员 / 群主管理员 / 有权限用户"""
        if not uid or uid == get_self_id():
            return "机器人自己"
        role = role_map.get(uid, "")
        if not role:
            return "不在群成员"
        if role in ("owner", "admin"):
            return "群主/管理员"
        from app.core.permission import permission_service
        if permission_service.check_user_permission(group_id, uid, 2):
            return "有权限"
        return None

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
