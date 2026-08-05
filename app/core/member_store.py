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
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


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
                extras     TEXT DEFAULT '{}', -- 扩展字段（JSON）
                PRIMARY KEY (group_id, user_id)
            )
            """)
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

    def record_message(self, group_id, user_id) -> None:
        """更新最后发言时间（仅更新已记录成员；未记录成员忽略）"""
        conn = self._get_connection()
        conn.execute(
            "UPDATE group_members SET last_active = ? WHERE group_id = ? AND user_id = ?",
            (self._now_str(), str(group_id), str(user_id)),
        )
        conn.commit()

    def record_leave(self, group_id, user_id) -> None:
        """退群/被踢时清理成员记录"""
        conn = self._get_connection()
        conn.execute(
            "DELETE FROM group_members WHERE group_id = ? AND user_id = ?",
            (str(group_id), str(user_id)),
        )
        conn.commit()

    # ---------- 查询 ----------

    def get_member(self, group_id, user_id) -> Optional[dict]:
        """获取单个成员状态；不存在返回 None"""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT group_id, user_id, join_time, last_active, extras "
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
            "extras": json.loads(row[4] or "{}"),
        }

    def get_members(self, group_id) -> list[dict]:
        """获取群内全部成员状态（按入群时间正序）"""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT group_id, user_id, join_time, last_active, extras "
            "FROM group_members WHERE group_id = ? ORDER BY join_time",
            (str(group_id),),
        ).fetchall()
        return [{
            "group_id": r[0], "user_id": r[1], "join_time": r[2],
            "last_active": r[3], "extras": json.loads(r[4] or "{}"),
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
