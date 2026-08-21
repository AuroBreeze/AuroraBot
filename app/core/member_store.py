"""
群成员状态存储（app/core/member_store.py）

成员维度数据：入群时间、最后发言时间、扩展字段（JSON，供业务状态机使用，
如段位登记/引导流程状态）。

- 独立数据库 ./store/db/member_store.db，表结构自解释
- 进程内共享单例（与权限库模式一致），连接使用 WAL
"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

import pytz

from api.Logger_owner import Logger
from config.env import TIMEZONE

DEFAULT_DB_PATH = os.path.join("store", "db", "member_store.db")
from app.core.timeutil import TIME_FORMAT


class MemberStore:
    """群成员状态存取"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.logger = Logger("member_store")
        self.db_path = db_path
        self.bj_tz = pytz.timezone(TIMEZONE)
        self.conn: Optional[sqlite3.Connection] = None

    # ---------- 连接与建表 ----------

    def _get_connection(self) -> sqlite3.Connection:
        if self.conn is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id   TEXT NOT NULL,
                user_id    TEXT NOT NULL,
                join_time  DATETIME,          -- 入群时间
                last_active DATETIME,         -- 最后发言时间
                nickname   TEXT,              -- 昵称（API 同步/消息事件保存）
                extras     TEXT DEFAULT '{}', -- 扩展字段（JSON）
                PRIMARY KEY (group_id, user_id)
            )
            """)
            # 批量补记录标记：已补过的群不再自动重复处理
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS group_backfill (
                group_id       TEXT PRIMARY KEY,
                backfill_time  DATETIME
            )
            """)
            # 存量库兼容：补 nickname 列（旧库无此列）
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(group_members)").fetchall()]
            if "nickname" not in cols:
                self.conn.execute("ALTER TABLE group_members ADD COLUMN nickname TEXT")
            self.conn.commit()
        return self.conn

    def _now_str(self) -> str:
        return datetime.now(self.bj_tz).strftime(TIME_FORMAT)

    # ---------- 记录 ----------

    def record_join(self, group_id, user_id, join_time: Optional[str] = None) -> None:
        """入群记录（新成员写入；重复入群覆盖入群时间）"""
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO group_members (group_id, user_id, join_time, last_active, extras) "
            "VALUES (?, ?, ?, ?, '{}')",
            (str(group_id), str(user_id), join_time or self._now_str(), None),
        )
        conn.commit()

    def ensure_member(self, group_id, user_id) -> bool:
        """
        存量成员补齐：仅当记录不存在时写入（INSERT OR IGNORE），
        保留已有成员的 join_time/extras 不被覆盖。返回是否新增。
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "INSERT OR IGNORE INTO group_members (group_id, user_id, join_time, last_active, extras) "
            "VALUES (?, ?, ?, NULL, '{}')",
            (str(group_id), str(user_id), self._now_str()),
        )
        conn.commit()
        return cursor.rowcount > 0

    def upsert_member(self, group_id, user_id, join_time: Optional[str] = None,
                      last_active: Optional[str] = None, nickname: Optional[str] = None) -> None:
        """
        API 活跃同步专用：新成员补记录，已有成员仅更新传入字段（不覆盖既有值/extras）。
        join_time/last_active 为 None 时不覆盖已有值；nickname 有值时总是更新（API 为权威来源）。
        新成员的 join_time 缺省用当前时间。
        """
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO group_members (group_id, user_id, join_time, last_active, nickname, extras) "
            "VALUES (?, ?, ?, ?, ?, '{}') "
            "ON CONFLICT(group_id, user_id) DO UPDATE SET "
            "  join_time = COALESCE(excluded.join_time, group_members.join_time), "
            "  last_active = COALESCE(excluded.last_active, group_members.last_active), "
            "  nickname = CASE WHEN excluded.nickname IS NOT NULL AND excluded.nickname != '' "
            "                 THEN excluded.nickname ELSE group_members.nickname END",
            (str(group_id), str(user_id), join_time or self._now_str(), last_active, nickname),
        )
        conn.commit()

    # ---------- 批量补记录标记 ----------

    def mark_backfilled(self, group_id) -> None:
        """标记某群已完成批量补记录（幂等）"""
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO group_backfill (group_id, backfill_time) VALUES (?, ?)",
            (str(group_id), self._now_str()),
        )
        conn.commit()

    def is_backfilled(self, group_id) -> bool:
        """该群是否已执行过批量补记录"""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT 1 FROM group_backfill WHERE group_id = ?", (str(group_id),)
        ).fetchone()
        return row is not None

    def record_message(self, group_id, user_id, nickname: Optional[str] = None) -> None:
        """更新最后发言时间（仅更新已记录成员；未记录成员忽略）。

        秒级去重：同一用户同一秒重复发言不重复写库/commit（减少高频写放大）；
        顺带保存发言者昵称（有值即更新，实时昵称为准）。
        """
        now = self._now_str()
        conn = self._get_connection()
        # 触发更新条件：last_active 变化（正常发言）或 昵称有值且与库中不同（同秒发言也能更新昵称）
        cur = conn.execute(
            "UPDATE group_members SET last_active = ?, "
            "  nickname = CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE nickname END "
            "WHERE group_id = ? AND user_id = ? "
            "  AND (last_active IS NULL OR last_active != ? "
            "       OR (? IS NOT NULL AND ? != '' AND (nickname IS NULL OR nickname != ?)))",
            (now, nickname, nickname, nickname,
             str(group_id), str(user_id),
             now, nickname, nickname, nickname),
        )
        if cur.rowcount:  # 实际有变化才 commit
            conn.commit()

    def record_leave(self, group_id, user_id) -> None:
        """退群/被踢时清理成员记录"""
        conn = self._get_connection()
        conn.execute(
            "DELETE FROM group_members WHERE group_id = ? AND user_id = ?",
            (str(group_id), str(user_id)),
        )
        conn.commit()

    def remove_members_not_in(self, group_id, user_ids) -> int:
        """按当前群成员列表清理已退群或被踢的成员记录。"""
        conn = self._get_connection()
        group_id = str(group_id)
        user_ids = {str(user_id) for user_id in user_ids if user_id}
        stored_ids = {
            row[0] for row in conn.execute(
                "SELECT user_id FROM group_members WHERE group_id = ?", (group_id,)
            ).fetchall()
        }
        removed_ids = stored_ids - user_ids
        if not removed_ids:
            return 0
        conn.executemany(
            "DELETE FROM group_members WHERE group_id = ? AND user_id = ?",
            ((group_id, user_id) for user_id in removed_ids),
        )
        conn.commit()
        return len(removed_ids)

    # ---------- 查询 ----------

    def get_member(self, group_id, user_id) -> Optional[dict]:
        """获取单个成员状态；不存在返回 None"""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT group_id, user_id, join_time, last_active, nickname, extras "
            "FROM group_members WHERE group_id = ? AND user_id = ?",
            (str(group_id), str(user_id)),
        ).fetchone()
        if row is None:
            return None
        return {
            "group_id": row[0],
            "user_id": row[1],
            "join_time": row[2],
            "last_active": row[3],
            "nickname": row[4],
            "extras": json.loads(row[5] or "{}"),
        }

    def get_members(self, group_id) -> list[dict]:
        """获取群内全部成员状态（按入群时间正序）"""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT group_id, user_id, join_time, last_active, nickname, extras "
            "FROM group_members WHERE group_id = ? ORDER BY join_time",
            (str(group_id),),
        ).fetchall()
        return [{
            "group_id": r[0], "user_id": r[1], "join_time": r[2],
            "last_active": r[3], "nickname": r[4], "extras": json.loads(r[5] or "{}"),
        } for r in rows]

    # ---------- 扩展字段 ----------

    def get_extras(self, group_id, user_id) -> dict:
        member = self.get_member(group_id, user_id)
        return member["extras"] if member else {}

    def set_extras(self, group_id, user_id, extras: dict) -> None:
        """整体替换扩展字段（JSON 存储）"""
        conn = self._get_connection()
        conn.execute(
            "UPDATE group_members SET extras = ? WHERE group_id = ? AND user_id = ?",
            (json.dumps(extras, ensure_ascii=False), str(group_id), str(user_id)),
        )
        conn.commit()

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None


# 全局单例
member_store = MemberStore()
