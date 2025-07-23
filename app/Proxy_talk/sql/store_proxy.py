import sqlite3
import threading
import time
from api.Logger_owner import Logger
from ..proxy_cfg import DB_PATH

class StoreProxy:
    """
    简单的QQ号授权存储系统
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(StoreProxy, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if hasattr(self, 'initialized'):
            return
            
        self.logger = Logger("Proxy_store")
        self.db_path = DB_PATH + "proxy_auth.db"
        self.conn = None
        self.auth_cache = {}  # 授权缓存 {qq_id: (is_authorized, timestamp)}
        self.cache_duration = 300  # 缓存有效期(秒)
        self.initialized = True

    def _get_connection(self):
        """获取数据库连接"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._init_db()
        return self.conn

    def _init_db(self):
        """初始化数据库表"""
        cursor = self.conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS authorized_qq (
            qq_id TEXT PRIMARY KEY,
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS whitelist_groups (
            group_id TEXT PRIMARY KEY,
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id)
        )
        """)
        self.conn.commit()

    def _is_cache_valid(self, timestamp):
        """检查缓存是否有效"""
        return time.time() - timestamp < self.cache_duration

    def add_qq(self, qq_id: str) -> bool:
        """
        添加授权QQ号
        
        :param qq_id: QQ号码
        :return: 成功返回True，失败返回False
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            INSERT OR IGNORE INTO authorized_qq (qq_id)
            VALUES (?)
            """, (qq_id,))
            
            conn.commit()
            
            # 更新缓存
            self.auth_cache[qq_id] = (True, time.time())
            return True
        except Exception as e:
            self.logger.error(f"添加QQ号失败: {e}")
            return False

    def remove_qq(self, qq_id: str) -> bool:
        """
        移除授权QQ号
        
        :param qq_id: QQ号码
        :return: 成功返回True，失败返回False
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            DELETE FROM authorized_qq 
            WHERE qq_id = ?
            """, (qq_id,))
            
            conn.commit()
            
            # 更新缓存
            self.auth_cache[qq_id] = (False, time.time())
            return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"移除QQ号失败: {e}")
            return False

    def is_authorized(self, qq_id: str) -> bool:
        """
        检查QQ号是否被授权
        
        :param qq_id: QQ号码
        :return: 已授权返回True，否则返回False
        """
        # 检查缓存
        if qq_id in self.auth_cache:
            is_auth, timestamp = self.auth_cache[qq_id]
            if self._is_cache_valid(timestamp):
                return is_auth
        
        # 缓存未命中或过期，查询数据库
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT COUNT(*) FROM authorized_qq 
            WHERE qq_id = ?
            """, (qq_id,))
            
            is_auth = cursor.fetchone()[0] > 0
            
            # 更新缓存
            self.auth_cache[qq_id] = (is_auth, time.time())
            return is_auth
        except Exception as e:
            self.logger.error(f"检查QQ号授权失败: {e}")
            return False

    def list_all(self) -> list:
        """
        列出所有授权QQ号
        
        :return: QQ号列表
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT qq_id FROM authorized_qq
            """)
            
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"列出授权QQ号失败: {e}")
            return []

    def add_group(self, group_id: str) -> bool:
        """
        添加白名单群组
        
        :param group_id: 群号
        :return: 成功返回True，失败返回False
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            INSERT OR IGNORE INTO whitelist_groups (group_id)
            VALUES (?)
            """, (group_id,))
            
            conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"添加白名单群组失败: {e}")
            return False

    def remove_group(self, group_id: str) -> bool:
        """
        移除白名单群组
        
        :param group_id: 群号
        :return: 成功返回True，失败返回False
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            DELETE FROM whitelist_groups 
            WHERE group_id = ?
            """, (group_id,))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"移除白名单群组失败: {e}")
            return False

    def is_whitelisted(self, group_id: str) -> bool:
        """
        检查群组是否在白名单
        
        :param group_id: 群号
        :return: 在白名单返回True，否则返回False
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT COUNT(*) FROM whitelist_groups 
            WHERE group_id = ?
            """, (group_id,))
            
            return cursor.fetchone()[0] > 0
        except Exception as e:
            self.logger.error(f"检查白名单群组失败: {e}")
            return False

    def list_groups(self) -> list:
        """
        列出所有白名单群组
        
        :return: 群号列表
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT group_id FROM whitelist_groups
            """)
            
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"列出白名单群组失败: {e}")
            return []

if __name__ == '__main__':
    store = StoreProxy()
    # 测试代码
    store.add_qq("123456")
    print(store.is_authorized("123456"))  # True
    store.remove_qq("123456")
    print(store.is_authorized("123456"))  # False