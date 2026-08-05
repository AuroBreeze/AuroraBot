import sqlite3
import json
from datetime import datetime, timedelta
import pytz
from api.Logger_owner import Logger
from config import env

class StoreAnnouncement:
    """
    定时喊话数据库存储
    """
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 确保只初始化一次
        if not self._initialized:
            self.logger = Logger("TimedAnnouncement_store")
            self.db_path = "./store/db/timed_announcement.db"
            self.timezone = env.TIMEZONE
            self.bj_tz = pytz.timezone(self.timezone)
            self.conn = None
            self._init_db()
            self.__class__._initialized = True

    def _get_connection(self):
        """获取数据库连接"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA foreign_keys = ON")
        return self.conn

    def _init_db(self):
        """初始化数据库表（安全模式，不会覆盖现有数据）"""
        try:
            import os
            db_exists = os.path.exists(self.db_path)
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='announcement_tasks'
            """)
            table_exists = cursor.fetchone() is not None
            
            if db_exists and table_exists:
                self.logger.info(f"数据库已存在，表结构完整: {self.db_path}")
                # 检查索引是否存在
                cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name LIKE 'idx_announcement_%'
                """)
                indexes = cursor.fetchall()
                self.logger.info(f"找到 {len(indexes)} 个索引")
                return
            
            # 创建定时喊话任务表（如果不存在）
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcement_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                message TEXT NOT NULL,
                hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
                minute INTEGER NOT NULL CHECK (minute >= 0 AND minute <= 59),
                days_of_week TEXT NOT NULL,  -- JSON数组，如[1,2,3,4,5,6,7]表示周一到周日
                enabled INTEGER DEFAULT 1,   -- 1启用，0禁用
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_executed DATETIME,
                UNIQUE(group_id, hour, minute, message)  -- 防止重复任务
            )
            """)
            
            # 创建索引（如果不存在）
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_announcement_enabled 
            ON announcement_tasks(enabled)
            """)
            
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_announcement_time 
            ON announcement_tasks(hour, minute)
            """)
            
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_announcement_group 
            ON announcement_tasks(group_id)
            """)
            
            conn.commit()
            
            if db_exists and not table_exists:
                self.logger.info(f"在现有数据库文件中创建了表结构: {self.db_path}")
            elif not db_exists:
                self.logger.info(f"创建了新的数据库文件: {self.db_path}")
            else:
                self.logger.info("定时喊话数据库初始化完成")
                
        except Exception as e:
            self.logger.error(f"初始化数据库失败: {e}")
            raise

    def add_announcement(self, group_id: str, creator_id: str, message: str, 
                        hour: int, minute: int, days_of_week: list) -> tuple[bool, str]:
        """
        添加定时喊话任务
        
        :param group_id: 群组ID
        :param creator_id: 创建者ID
        :param message: 喊话内容
        :param hour: 小时 (0-23)
        :param minute: 分钟 (0-59)
        :param days_of_week: 星期几列表 [1-7] 1=周一，7=周日
        :return: (是否成功, 消息)
        """
        try:
            # 验证参数
            if not 0 <= hour <= 23:
                return False, "小时必须在0-23之间"
            if not 0 <= minute <= 59:
                return False, "分钟必须在0-59之间"
            if not days_of_week:
                return False, "必须指定至少一个星期几"
            if not all(1 <= day <= 7 for day in days_of_week):
                return False, "星期几必须在1-7之间"
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 检查是否已存在相同任务
            cursor.execute("""
            SELECT COUNT(*) FROM announcement_tasks 
            WHERE group_id = ? AND hour = ? AND minute = ? AND message = ?
            """, (group_id, hour, minute, message))
            
            if cursor.fetchone()[0] > 0:
                return False, "已存在相同的定时喊话任务"
            
            # 插入新任务
            cursor.execute("""
            INSERT INTO announcement_tasks 
            (group_id, creator_id, message, hour, minute, days_of_week, enabled)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (group_id, creator_id, message, hour, minute, json.dumps(days_of_week)))
            
            conn.commit()
            task_id = cursor.lastrowid
            return True, f"定时喊话任务添加成功，ID: {task_id}"
            
        except Exception as e:
            self.logger.error(f"添加定时喊话任务失败: {e}")
            return False, f"添加定时喊话任务失败: {str(e)}"

    def delete_announcement(self, task_id: int, user_id: str) -> tuple[bool, str]:
        """
        删除定时喊话任务
        
        :param task_id: 任务ID
        :param user_id: 用户ID（用于权限验证）
        :return: (是否成功, 消息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 检查任务是否存在
            cursor.execute("""
            SELECT creator_id FROM announcement_tasks WHERE id = ?
            """, (task_id,))
            
            result = cursor.fetchone()
            if not result:
                return False, "定时喊话任务不存在"
            
            # 检查权限（只有创建者可以删除）
            creator_id = result[0]
            if creator_id != user_id:
                return False, "只有任务创建者可以删除该任务"
            
            # 删除任务
            cursor.execute("""
            DELETE FROM announcement_tasks WHERE id = ?
            """, (task_id,))
            
            conn.commit()
            return True, "定时喊话任务删除成功"
            
        except Exception as e:
            self.logger.error(f"删除定时喊话任务失败: {e}")
            return False, f"删除定时喊话任务失败: {str(e)}"

    def list_announcements(self, group_id: str = None, user_id: str = None) -> tuple[list, str]:
        """
        列出定时喊话任务
        
        :param group_id: 群组ID（可选）
        :param user_id: 用户ID（可选）
        :return: (任务列表, 消息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            query = "SELECT * FROM announcement_tasks"
            params = []
            
            conditions = []
            if group_id:
                conditions.append("group_id = ?")
                params.append(group_id)
            if user_id:
                conditions.append("creator_id = ?")
                params.append(user_id)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY hour, minute"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # 格式化结果
            tasks = []
            for row in rows:
                task = {
                    'id': row[0],
                    'group_id': row[1],
                    'creator_id': row[2],
                    'message': row[3],
                    'hour': row[4],
                    'minute': row[5],
                    'days_of_week': json.loads(row[6]),
                    'enabled': bool(row[7]),
                    'created_time': row[8],
                    'last_executed': row[9]
                }
                tasks.append(task)
            
            return tasks, "查询成功"
            
        except Exception as e:
            self.logger.error(f"查询定时喊话任务失败: {e}")
            return [], f"查询定时喊话任务失败: {str(e)}"

    def toggle_announcement(self, task_id: int, user_id: str) -> tuple[bool, str]:
        """
        切换定时喊话任务状态（启用/禁用）
        
        :param task_id: 任务ID
        :param user_id: 用户ID（用于权限验证）
        :return: (是否成功, 消息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 检查任务是否存在
            cursor.execute("""
            SELECT creator_id, enabled FROM announcement_tasks WHERE id = ?
            """, (task_id,))
            
            result = cursor.fetchone()
            if not result:
                return False, "定时喊话任务不存在"
            
            # 检查权限（只有创建者可以切换状态）
            creator_id = result[0]
            if creator_id != user_id:
                return False, "只有任务创建者可以切换任务状态"
            
            current_enabled = result[1]
            new_enabled = 0 if current_enabled else 1
            
            # 更新状态
            cursor.execute("""
            UPDATE announcement_tasks SET enabled = ? WHERE id = ?
            """, (new_enabled, task_id))
            
            conn.commit()
            status = "启用" if new_enabled else "禁用"
            return True, f"定时喊话任务已{status}"
            
        except Exception as e:
            self.logger.error(f"切换定时喊话任务状态失败: {e}")
            return False, f"切换定时喊话任务状态失败: {str(e)}"

    def get_due_announcements(self) -> list:
        """
        获取当前时间需要执行的喊话任务
        
        :return: 需要执行的任务列表
        """
        try:
            now = datetime.now(self.bj_tz)
            current_hour = now.hour
            current_minute = now.minute
            current_weekday = now.isoweekday()  # 1=周一，7=周日
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 查询当前时间需要执行的任务
            cursor.execute("""
            SELECT id, group_id, message, days_of_week, last_executed 
            FROM announcement_tasks 
            WHERE enabled = 1 AND hour = ? AND minute = ?
            """, (current_hour, current_minute))
            
            due_tasks = []
            for row in cursor.fetchall():
                task_id, group_id, message, days_of_week_json, last_executed = row
                days_of_week = json.loads(days_of_week_json)
                
                # 检查今天是否需要执行
                if current_weekday in days_of_week:
                    # 检查今天是否已经执行过
                    if last_executed:
                        last_executed_dt = datetime.fromisoformat(last_executed)
                        if last_executed_dt.date() == now.date():
                            continue  # 今天已经执行过
                    
                    due_tasks.append({
                        'id': task_id,
                        'group_id': group_id,
                        'message': message
                    })
            
            return due_tasks
            
        except Exception as e:
            self.logger.error(f"获取待执行任务失败: {e}")
            return []

    def update_last_executed(self, task_id: int):
        """
        更新任务最后执行时间
        
        :param task_id: 任务ID
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            now = datetime.now(self.bj_tz).isoformat()
            cursor.execute("""
            UPDATE announcement_tasks SET last_executed = ? WHERE id = ?
            """, (now, task_id))
            
            conn.commit()
        except Exception as e:
            self.logger.error(f"更新最后执行时间失败: {e}")

    def clear_old_tasks(self, days: int = 30):
        """
        清理旧的任务记录
        
        :param days: 保留天数
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cutoff_date = (datetime.now(self.bj_tz) - timedelta(days=days)).isoformat()
            cursor.execute("""
            DELETE FROM announcement_tasks 
            WHERE created_time < ? AND enabled = 0
            """, (cutoff_date,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            if deleted_count > 0:
                self.logger.info(f"清理了 {deleted_count} 个旧的禁用任务")
                
        except Exception as e:
            self.logger.error(f"清理旧任务失败: {e}")

    def __del__(self):
        """清理连接"""
        if self.conn:
            self.conn.close()