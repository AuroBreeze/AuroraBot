import sqlite3
from api.Logger_owner import Logger
from ..proxy_cfg import DB_PATH

class StoreProxy:
    """
    简单的QQ号授权存储系统
    """
    def __init__(self):
        self.logger = Logger("Proxy_store")
        self.db_path = DB_PATH + "proxy_auth.db"  # 简化路径
        self.conn = None

    def _get_connection(self):
        """获取数据库连接"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
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
        self.conn.commit()

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
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT COUNT(*) FROM authorized_qq 
            WHERE qq_id = ?
            """, (qq_id,))
            
            return cursor.fetchone()[0] > 0
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

if __name__ == '__main__':
    store = StoreProxy()
    # 测试代码
    store.add_qq("123456")
    print(store.is_authorized("123456"))  # True
    store.remove_qq("123456")
    print(store.is_authorized("123456"))  # False
