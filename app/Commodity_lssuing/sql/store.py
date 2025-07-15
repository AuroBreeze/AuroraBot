import sqlite3
from .. import manage_cfg
from api.Logger_owner import Logger
import pytz
from datetime import datetime

class Store:
    """
    商品存储数据库，用来存储商品信息
    """
    def __init__(self):
        self.logger = Logger("Commodity_store")
        self.db_path = manage_cfg.DB_PATH + "commodity_store.db"
        self.timezone = "Asia/Shanghai"
        self.bj_tz = pytz.timezone(self.timezone)
        self.conn = None

    def _get_connection(self):
        """获取数据库连接"""
        if not self.conn:
            self.conn = sqlite3.connect(self.db_path)
            # 启用外键约束
            self.conn.execute("PRAGMA foreign_keys = ON")
            self._init_db()
        return self.conn

    def _init_db(self):
        """初始化商品数据库表"""
        cursor = self.conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS commodities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,          -- 商品名称
            chinese_name TEXT NOT NULL,  -- 中文名称
            price REAL NOT NULL,         -- 售价
            notes TEXT,                 -- 备注
            is_welfare BOOLEAN DEFAULT FALSE,  -- 是否为福利商品
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name)
        )
        """)

        # 创建购买记录表(仅记录消费信息)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,     -- 群号
            qq_id TEXT NOT NULL,         -- QQ号
            amount REAL NOT NULL,        -- 消费金额
            purchase_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 创建商品持有表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS plugin_ownership (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qq_id TEXT NOT NULL,         -- QQ号
            plugin_id TEXT NOT NULL,     -- 商品ID
            purchase_id INTEGER,         -- 关联的购买记录ID
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP, -- 购买时间
            FOREIGN KEY (purchase_id) REFERENCES purchase_records(id) ON DELETE SET NULL
            FOREIGN KEY (qq_id) REFERENCES users(qq_id) ON DELETE CASCADE -- 约束用户表的删除行为
        )
        """)

        # 创建索引
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_commodity_name 
        ON commodities(name)
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_commodity_chinese_name 
        ON commodities(chinese_name)
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_purchase_group 
        ON purchase_records(group_id)
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_purchase_qq 
        ON purchase_records(qq_id)
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_plugin_owner 
        ON plugin_ownership(qq_id)
        """)

        # 创建商品状态表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS plugin_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_name TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (plugin_name) REFERENCES commodities(name) ON DELETE CASCADE,
            UNIQUE(plugin_name)
        )
        """)

        # 创建商品状态索引
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_plugin_status 
        ON plugin_status(plugin_name)
        """)
        
        self.conn.commit()
    def add_commodity(self, name: str, chinese_name: str, price: float, notes: str = None, is_welfare: bool = False) -> tuple[bool, str]:
        """
        添加商品
    
        :param name: 商品名称
        :param chinese_name: 中文名称
        :param price: 售价
        :param notes: 备注(可选)
        :param is_welfare: 是否为福利商品(默认False)
        :return: (是否成功, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
        
            # 先检查商品是否存在
            cursor.execute("SELECT 1 FROM commodities WHERE name = ?", (name,))
            if cursor.fetchone():
                return False, f"商品 {name} 已存在"
            
            # 开始事务
            conn.execute("BEGIN TRANSACTION")
            
            try:
                # 添加新商品
                cursor.execute("""
                INSERT INTO commodities (name, chinese_name, price, notes, is_welfare)
                VALUES (?, ?, ?, ?, ?)
                """, (name, chinese_name, price, notes, is_welfare))
                
                # 默认设置为上架状态
                cursor.execute("""
                INSERT INTO plugin_status (plugin_name, is_active)
                VALUES (?, TRUE)
                """, (name,))
                
                conn.commit()
                return True, f"商品 {name}({chinese_name}) 添加成功并已上架"
                
            except Exception as e:
                conn.rollback()
                raise e
        except Exception as e:
            self.logger.error(f"添加商品失败: {e}")
            return False, f"添加商品失败: {e}"

    def update_commodity(self, name: str, chinese_name: str = None, price: float = None, notes: str = None, is_welfare: bool = None) -> tuple[bool, str]:
        """
        更新商品信息
    
        :param name: 商品名称(用于查找)
        :param chinese_name: 新中文名称(可选)
        :param price: 新售价(可选)
        :param notes: 新备注(可选)
        :param is_welfare: 是否为福利商品(可选)
        :return: (是否成功, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
        
            # 先检查商品是否存在
            cursor.execute("SELECT 1 FROM commodities WHERE name = ?", (name,))
            if not cursor.fetchone():
                return False, f"商品 {name} 不存在"
            
            # 构建更新语句
            updates = []
            params = []
        
            if chinese_name is not None:
                updates.append("chinese_name = ?")
                params.append(chinese_name)
            
            if price is not None:
                updates.append("price = ?")
                params.append(price)
            
            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)
            
            if is_welfare is not None:
                updates.append("is_welfare = ?")
                params.append(is_welfare)
            
            if not updates:
                return False, "没有提供更新内容"
            
            # 添加更新时间
            updates.append("update_time = CURRENT_TIMESTAMP")
        
            params.append(name)  # 最后添加WHERE条件参数
        
            query = f"""
            UPDATE commodities 
            SET {', '.join(updates)}
            WHERE name = ?
            """
        
            cursor.execute(query, params)
            conn.commit()
            return True, f"商品 {name} 更新成功"
        except Exception as e:
            self.logger.error(f"更新商品失败: {e}")
            return False, f"更新商品失败: {e}"

    def get_commodity(self, name: str) -> tuple[dict, str]:
        """
        获取商品信息
        
        :param name: 商品名称
        :return: (商品信息字典, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT name, chinese_name, price, notes, is_welfare 
            FROM commodities 
            WHERE name = ?
            """, (name,))
            
            result = cursor.fetchone()
            if not result:
                return None, f"商品 {name} 不存在"
                
            return {
                "name": result[0],
                "chinese_name": result[1],
                "price": result[2],
                "notes": result[3],
                "is_welfare": bool(result[4])
            }, None
        except Exception as e:
            self.logger.error(f"获取商品信息失败: {e}")
            return None, f"获取商品信息失败: {e}"

    def delete_commodity(self, name: str) -> tuple[bool, str]:
        """
        删除商品
        
        :param name: 商品名称
        :return: (是否成功, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            DELETE FROM commodities 
            WHERE name = ?
            """, (name,))
            
            if cursor.rowcount == 0:
                return False, f"商品 {name} 不存在"
                
            conn.commit()
            return True, f"商品 {name} 删除成功"
        except Exception as e:
            self.logger.error(f"删除商品失败: {e}")
            return False, f"删除商品失败: {e}"

    def list_commodities(self) -> tuple[list, str]:
        """
        列出所有商品
        
        :return: (商品列表, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT name, chinese_name, price, notes, is_welfare 
            FROM commodities 
            ORDER BY name
            """)
            
            results = cursor.fetchall()
            commodities = []
            
            for row in results:
                commodities.append({
                    "name": row[0],
                    "chinese_name": row[1],
                    "price": row[2],
                    "notes": row[3],
                    "is_welfare": bool(row[4])
                })
                
            return commodities, None
        except Exception as e:
            self.logger.error(f"列出商品失败: {e}")
            return [], f"列出商品失败: {e}"

    def search_commodities(self, keyword: str) -> tuple[list, str]:
        """
        搜索商品(按名称或中文名称)
        
        :param keyword: 搜索关键词
        :return: (商品列表, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT name, chinese_name, price, notes, is_welfare 
            FROM commodities 
            WHERE name LIKE ? OR chinese_name LIKE ?
            ORDER BY name
            """, (f"%{keyword}%", f"%{keyword}%"))
            
            results = cursor.fetchall()
            commodities = []
            
            for row in results:
                commodities.append({
                    "name": row[0],
                    "chinese_name": row[1],
                    "price": row[2],
                    "notes": row[3],
                    "is_welfare": bool(row[4])
                })
                
            return commodities, None
        except Exception as e:
            self.logger.error(f"搜索商品失败: {e}")
            return [], f"搜索商品失败: {e}"

    def add_purchase_record(self, group_id: str, qq_id: str, amount: float) -> tuple[bool, int, str]:
        """
        添加购买记录(仅记录消费)
        
        :param group_id: 群号
        :param qq_id: QQ号
        :param amount: 消费金额
        :return: (是否成功, 记录ID, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
            INSERT INTO purchase_records (group_id, qq_id, amount)
            VALUES (?, ?, ?)
            """, (group_id, qq_id, amount))
            
            record_id = cursor.lastrowid
            conn.commit()
            return True, record_id, f"群{group_id}用户{qq_id}消费记录添加成功"
        except Exception as e:
            self.logger.error(f"添加购买记录失败: {e}")
            return False, f"添加购买记录失败: {e}"

    def get_purchase_records(self, group_id: str = None, qq_id: str = None) -> tuple[list, str]:
        """
        获取消费记录
        
        :param group_id: 群号(可选)
        :param qq_id: QQ号(可选)
        :return: (消费记录列表, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            query = """
            SELECT id, group_id, qq_id, amount, purchase_time
            FROM purchase_records
            """
            params = []

            conditions = []
            if group_id:
                conditions.append("group_id = ?")
                params.append(group_id)
            if qq_id:
                conditions.append("qq_id = ?")
                params.append(qq_id)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY purchase_time DESC"

            cursor.execute(query, params)
            
            results = cursor.fetchall()
            records = []
            
            for row in results:
                records.append({
                    "id": row[0],
                    "group_id": row[1],
                    "qq_id": row[2],
                    "amount": row[3],
                    "purchase_time": row[4]
                })
                
            return records, None
        except Exception as e:
            self.logger.error(f"获取购买记录失败: {e}")
            return [], f"获取购买记录失败: {e}"

    def add_plugin_ownership(self, qq_id: str, plugin_id: str, purchase_id: int) -> tuple[bool, str]:
        """
        添加商品持有记录
        
        :param qq_id: QQ号
        :param plugin_id: 商品ID
        :param purchase_id: 关联的购买记录ID
        :return: (是否成功, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
            INSERT INTO plugin_ownership (qq_id, plugin_id, purchase_id)
            VALUES (?, ?, ?)
            """, (qq_id, plugin_id, purchase_id))
            
            conn.commit()
            return True, f"用户{qq_id}商品{plugin_id}持有记录添加成功"
        except Exception as e:
            self.logger.error(f"添加商品持有记录失败: {e}")
            return False, f"添加商品持有记录失败: {e}"

    def get_user_plugins(self, qq_id: str) -> tuple[list, str]:
        """
        获取用户持有的商品
        
        :param qq_id: QQ号
        :return: (商品列表, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
            SELECT plugin_id 
            FROM plugin_ownership 
            WHERE qq_id = ?
            ORDER BY create_time DESC
            """, (qq_id,))
            
            results = cursor.fetchall()
            plugins = []
            
            for row in results:
                plugins.append({
                    "plugin_id": row[0]
                })
                
            return plugins, None
        except Exception as e:
            self.logger.error(f"获取用户商品失败: {e}")
            return [], f"获取用户商品失败: {e}"

    def get_group_purchase_summary(self, group_id: str) -> tuple[dict, str]:
        """
        获取群组消费汇总
        
        :param group_id: 群号
        :return: (汇总信息, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 获取总消费额
            cursor.execute("""
            SELECT SUM(amount) FROM purchase_records WHERE group_id = ?
            """, (group_id,))
            total_amount = cursor.fetchone()[0] or 0

            # 获取购买人数
            cursor.execute("""
            SELECT COUNT(DISTINCT qq_id) FROM purchase_records WHERE group_id = ?
            """, (group_id,))
            buyer_count = cursor.fetchone()[0] or 0

            return {
                "total_amount": total_amount,
                "buyer_count": buyer_count
            }, None
        except Exception as e:
            self.logger.error(f"获取群组消费汇总失败: {e}")
            return None, f"获取群组消费汇总失败: {e}"

    def update_plugin_status(self, plugin_name: str, is_active: bool) -> tuple[bool, str]:
        """
        更新商品上下架状态
        
        :param plugin_id: 商品ID
        :param is_active: 是否上架
        :return: (是否成功, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 先检查商品是否存在
            cursor.execute("SELECT 1 FROM plugin_status WHERE plugin_name = ?", (plugin_name,))
            if not cursor.fetchone():
                return False, f"商品 {plugin_name} 不存在"

            # 更新或插入状态记录
            cursor.execute("""
            INSERT OR REPLACE INTO plugin_status (plugin_name, is_active)
            VALUES (?, ?)
            """, (plugin_name, is_active))
            
            conn.commit()
            status = "上架" if is_active else "下架"
            return True, f"商品 {plugin_name} 已{status}"
        except Exception as e:
            self.logger.error(f"更新商品状态失败: {e}")
            return False, f"更新商品状态失败: {e}"

    def get_plugin_status(self, plugin_name: str) -> tuple[bool, str]:
        """
        获取商品状态
        
        :param plugin_id: 商品ID
        :return: (是否上架, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
            SELECT is_active FROM plugin_status 
            WHERE plugin_name = ?
            """, (plugin_name,))
            
            result = cursor.fetchone()
            if not result:
                # 默认返回True(上架)如果记录不存在
                return True, None
                
            return bool(result[0]), None
        except Exception as e:
            self.logger.error(f"获取商品状态失败: {e}")
            return False, f"获取商品状态失败: {e}"

    def list_plugins_state(self,state:str = "TRUE") -> tuple[list, str]:
        """
        列出所有上架商品
        
        :return: (商品列表, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            if state == "TRUE":
                cursor.execute("""
                SELECT plugin_name FROM plugin_status 
                WHERE is_active = TRUE
                """)
            elif state == "FALSE":
                cursor.execute("""
                SELECT plugin_name FROM plugin_status 
                WHERE is_active = FALSE
                """)
            else:
                return [], "函数list_plugins_state()参数错误"
            
            results = cursor.fetchall()
            plugins = [{"plugin_name": row[0]} for row in results]
            return plugins, None
        except Exception as e:
            if state == "TRUE":
                self.logger.error(f"列出上架商品失败: {e}")
            else:
                self.logger.error(f"列出下架商品失败: {e}")
            return [], f"列出商品失败: {e}"


    def __str__(self):
        return "商品存储数据库(包含购买记录、商品持有记录和商品状态)"

if __name__ == '__main__':
    store = Store()
    print(store)
