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
            price REAL NOT NULL,         -- 售价
            notes TEXT,                 -- 备注
            is_welfare BOOLEAN DEFAULT FALSE,  -- 是否为福利商品
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name)
        )
        """)

        # 创建购买记录表（移除 group_id 列）
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qq_id TEXT NOT NULL,         -- QQ号
            amount REAL NOT NULL,        -- 消费金额
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(qq_id)  -- 唯一约束改为 qq_id
        )
        """)

        # 创建商品持有表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS plugin_ownership (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qq_id TEXT NOT NULL,         -- QQ号
            plugin_name TEXT NOT NULL,   -- 商品名称
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP, -- 购买时间
            FOREIGN KEY (qq_id) REFERENCES purchase_records(qq_id) ON DELETE CASCADE, -- 约束用户表的删除行为
            FOREIGN KEY (plugin_name) REFERENCES commodities(name) ON DELETE CASCADE, -- 约束商品表的删除行为
            UNIQUE (qq_id, plugin_name)
        )
        """)

        # 创建索引
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_commodity_name 
        ON commodities(name)
        """)
        
        cursor.execute("""
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
    def add_commodity(self, name: str, price: float, notes: str = None, is_welfare: bool = False) -> tuple[bool, str]:
        """
        添加商品
    
        :param name: 商品名称
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
                INSERT INTO commodities (name, price, notes, is_welfare)
                VALUES (?, ?, ?, ?)
                """, (name, price, notes, is_welfare))
                
                # 默认设置为上架状态
                cursor.execute("""
                INSERT INTO plugin_status (plugin_name, is_active)
                VALUES (?, TRUE)
                """, (name,))
                
                conn.commit()
                return True, f"商品 {name} 添加成功并已上架"
                
            except Exception as e:
                conn.rollback()
                raise e
        except Exception as e:
            self.logger.error(f"添加商品失败: {e}")
            return False, f"添加商品失败: {e}"

    def update_commodity(self, name: str, price: float = None, notes: str = None, is_welfare: bool = None) -> tuple[bool, str]:
        """
        更新商品信息
    
        :param name: 商品名称(用于查找)
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
            SELECT name, price, notes, is_welfare 
            FROM commodities 
            WHERE name = ?
            """, (name,))
            
            result = cursor.fetchone()
            if not result:
                return None, f"商品 {name} 不存在"
                
            return {
                "name": result[0],
                "price": result[1],
                "notes": result[2],
                "is_welfare": bool(result[3])
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
            SELECT name, price, notes, is_welfare 
            FROM commodities 
            ORDER BY name
            """)
            
            results = cursor.fetchall()
            commodities = []
            
            for row in results:
                commodities.append({
                    "name": row[0],
                    "price": row[1],
                    "notes": row[2],
                    "is_welfare": bool(row[3])
                })
                
            return commodities, None
        except Exception as e:
            self.logger.error(f"列出商品失败: {e}")
            return [], f"列出商品失败: {e}"

    def search_commodities(self, keyword: str) -> tuple[list, str]:
        """
        搜索商品(按名称)
        
        :param keyword: 搜索关键词
        :return: (商品列表, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT name, price, notes, is_welfare 
            FROM commodities 
            WHERE name LIKE ?
            ORDER BY name
            """, (f"%{keyword}%",))
            
            results = cursor.fetchall()
            commodities = []
            
            for row in results:
                commodities.append({
                    "name": row[0],
                    "price": row[1],
                    "notes": row[2],
                    "is_welfare": bool(row[3])
                })
                
            return commodities, None
        except Exception as e:
            self.logger.error(f"搜索商品失败: {e}")
            return [], f"搜索商品失败: {e}"

    def add_purchase_record(self, qq_id: str, amount: float) -> tuple[bool, int, str]:
        """
        添加购买记录(仅记录消费)
        
        :param qq_id: QQ号
        :param amount: 消费金额
        :return: (是否成功, 记录ID, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 先检查记录是否存在（移除 group_id 条件）
            cursor.execute("""
            SELECT id, amount FROM purchase_records 
            WHERE qq_id = ?
            """, (qq_id,))
            existing_record = cursor.fetchone()
            
            if existing_record:
                # 存在则更新金额
                record_id = existing_record[0]
                new_amount = existing_record[1] + amount
                cursor.execute("""
                UPDATE purchase_records 
                SET amount = ?, update_time = CURRENT_TIMESTAMP 
                WHERE id = ?
                """, (new_amount, record_id))
                conn.commit()
                return True, record_id, f"用户{qq_id}消费记录更新成功，总金额{new_amount:.2f}"
            else:
                # 不存在则插入新记录（移除 group_id）
                cursor.execute("""
                INSERT INTO purchase_records (qq_id, amount)
                VALUES (?, ?)
                """, (qq_id, amount))
                record_id = cursor.lastrowid
                conn.commit()
                return True, record_id, f"用户{qq_id}消费记录添加成功"
                
        except Exception as e:
            self.logger.error(f"添加/更新购买记录失败: {e}")
            return False, None, f"添加/更新购买记录失败: {e}"

    def get_purchase_records(self, qq_id: str = None) -> tuple[list, str]:
        """
        获取消费记录
        
        :param qq_id: QQ号(可选)
        :return: (消费记录列表, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            query = """
            SELECT id, qq_id, amount, update_time
            FROM purchase_records
            """
            params = []

            if qq_id:
                query += " WHERE qq_id = ?"
                params.append(qq_id)

            query += " ORDER BY update_time DESC"

            cursor.execute(query, params)
            
            results = cursor.fetchall()
            records = []
            
            for row in results:
                records.append({
                    "id": row[0],
                    "qq_id": row[1],
                    "amount": row[2],
                    "update_time": row[3]
                })
                
            return records, None
        except Exception as e:
            self.logger.error(f"获取购买记录失败: {e}")
            return [], f"获取购买记录失败: {e}"

    def add_plugin_ownership(self, qq_id: str, plugin_name: str, amount: float = None) -> tuple[bool, str]:
        """
        添加商品持有记录并记录购买信息
        
        :param qq_id: QQ号
        :param plugin_name: 商品名称
        :param amount: 消费金额(可选，如果None则查询商品价格)
        :return: (是否成功, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 开始事务
            conn.execute("BEGIN TRANSACTION")
            
            try:
                # 检查用户是否已持有该商品
                cursor.execute("""
                SELECT 1 FROM plugin_ownership 
                WHERE qq_id = ? AND plugin_name = ?
                """, (qq_id, plugin_name))
                if cursor.fetchone():
                    conn.commit()
                    return False, f"用户 {qq_id} 已持有商品 {plugin_name}"

                # 检查商品是否为福利商品
                cursor.execute("""
                SELECT is_welfare FROM commodities 
                WHERE name = ?
                """, (plugin_name,))
                result = cursor.fetchone()
                if not result:
                    conn.commit()
                    return False, f"商品 {plugin_name} 不存在"
                
                is_welfare = bool(result[0])

                # 获取商品价格(如果amount未提供)
                if amount is None:
                    cursor.execute("SELECT price FROM commodities WHERE name = ?", (plugin_name,))
                    result = cursor.fetchone()
                    if not result:
                        conn.commit()
                        return False, f"商品 {plugin_name} 不存在"
                    
                    amount = 0 if is_welfare else result[0]  # 福利商品amount设为0

                # 添加购买记录
                self.add_purchase_record(qq_id, amount)
                
                # 添加商品持有记录
                cursor.execute("""
                INSERT INTO plugin_ownership (qq_id, plugin_name)
                VALUES (?, ?)
                """, (qq_id, plugin_name))

                success, welfare_msg = self.auto_grant_welfare_commodities(qq_id)
                conn.commit()
                msg = f"用户 {qq_id} 商品{plugin_name}持有记录添加成功，消费金额{amount}已记录"
                if welfare_msg:
                    msg += f"\n{welfare_msg}"

                return True, msg
            except Exception as e:
                conn.rollback()
                raise e
        except Exception as e:
            self.logger.error(f"添加商品持有记录失败: {e}")
            return False, f"添加商品持有记录失败: {e}"

    def remove_plugin_ownership(self, qq_id: str, plugin_name: str) -> tuple[bool, str]:
        """
        删除用户商品持有记录并减少消费金额
        
        :param qq_id: 用户QQ号
        :param plugin_name: 商品名称
        :return: (是否成功, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 开始事务
            conn.execute("BEGIN TRANSACTION")
            
            try:
                # 检查记录是否存在
                cursor.execute("""
                SELECT 1 FROM plugin_ownership 
                WHERE qq_id = ? AND plugin_name = ?
                """, (qq_id, plugin_name))
                
                if not cursor.fetchone():
                    conn.commit()
                    return False, f"用户 {qq_id} 未持有商品 {plugin_name}"

                # 获取商品价格（福利商品价格为0）
                cursor.execute("""
                SELECT price, is_welfare FROM commodities
                WHERE name = ?
                """, (plugin_name,))
                result = cursor.fetchone()
                if not result:
                    conn.commit()
                    return False, f"商品 {plugin_name} 不存在"
                
                price = 0 if result[1] else result[0]  # 福利商品价格为0

                # 更新消费记录（减少金额）
                cursor.execute("""
                UPDATE purchase_records
                SET amount = amount - ?, update_time = CURRENT_TIMESTAMP
                WHERE qq_id = ?
                """, (price, qq_id))

                # 删除商品持有记录
                cursor.execute("""
                DELETE FROM plugin_ownership 
                WHERE qq_id = ? AND plugin_name = ?
                """, (qq_id, plugin_name))
                
                conn.commit()
                return True, f"已删除用户 {qq_id} 的商品 {plugin_name}，并减少消费金额{price}"
            except Exception as e:
                conn.rollback()
                raise e
        except Exception as e:
            self.logger.error(f"删除用户商品持有记录失败: {e}")
            return False, f"删除用户商品持有记录失败: {e}"

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
            SELECT plugin_name 
            FROM plugin_ownership 
            WHERE qq_id = ?
            ORDER BY create_time DESC
            """, (qq_id,))
            
            results = cursor.fetchall()
            plugins = []
            
            for row in results:
                plugins.append({
                    "plugin_name": row[0]
                })
                
            return plugins, None
        except Exception as e:
            self.logger.error(f"获取用户商品失败: {e}")
            return [], f"获取用户商品失败: {e}"

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

    def list_plugins_state(self, state: str = "TRUE") -> tuple[list, str]:
        """
        列出所有上架/下架商品(包含是否为福利商品信息)
        
        :param state: "TRUE"为上架商品，"FALSE"为下架商品
        :return: (商品列表, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            if state == "TRUE":
                cursor.execute("""
                SELECT ps.plugin_name, c.is_welfare 
                FROM plugin_status ps
                JOIN commodities c ON ps.plugin_name = c.name
                WHERE ps.is_active = TRUE
                """)
            elif state == "FALSE":
                cursor.execute("""
                SELECT ps.plugin_name, c.is_welfare 
                FROM plugin_status ps
                JOIN commodities c ON ps.plugin_name = c.name
                WHERE ps.is_active = FALSE
                """)
            else:
                return [], "函数list_plugins_state()参数错误"
            
            results = cursor.fetchall()
            plugins = [{
                "plugin_name": row[0],
                "is_welfare": bool(row[1])
            } for row in results]
            return plugins, None
        except Exception as e:
            if state == "TRUE":
                self.logger.error(f"列出上架商品失败: {e}")
            else:
                self.logger.error(f"列出下架商品失败: {e}")
            return [], f"列出商品失败: {e}"


    def list_user_info(self, qq_id: str) -> tuple[dict, str]:
        """
        获取用户信息(拥有的插件和消费金额)
        
        :param qq_id: QQ号
        :return: (用户信息字典, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 获取用户拥有的插件
            plugins, err = self.get_user_plugins(qq_id)
            if err:
                return None, err

            # 获取插件详细信息
            plugin_details = []
            for plugin in plugins:
                commodity, err = self.get_commodity(plugin["plugin_name"])
                if err:
                    continue  # 跳过无效商品
                plugin_details.append({
                    "name": commodity["name"],
                    "price": commodity["price"],
                    "notes": commodity["notes"],
                    "is_welfare": commodity["is_welfare"]
                })

            # 获取消费记录（移除 group_id 参数）
            records, err = self.get_purchase_records(qq_id=qq_id)
            if err:
                return None, err

            # 计算总消费金额
            total_spent = sum(record["amount"] for record in records)
            
            # 获取最近消费时间
            latest_purchase = max(record["update_time"] for record in records) if records else None

            return {
                "qq_id": qq_id,
                "plugins": plugin_details,
                "total_spent": total_spent,
                "latest_purchase": latest_purchase,
                "purchase_count": len(records)
            }, None

        except Exception as e:
            self.logger.error(f"获取用户信息失败: {e}")
            return None, f"获取用户信息失败: {e}"

    def auto_grant_welfare_commodities(self, qq_id: str) -> tuple[bool, str]:
        """
        自动发放符合条件的福利商品
        1. 检查用户消费金额是否达到福利商品价格
        2. 检查商品是否为上架状态
        3. 自动发放符合条件的福利商品
        
        :param qq_id: 用户QQ号
        :return: (是否成功, 错误信息)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 1. 获取用户消费总额
            cursor.execute("""
            SELECT amount FROM purchase_records 
            WHERE qq_id = ?
            """, (qq_id,))
            record = cursor.fetchone()
            if not record:
                return False, f"用户 {qq_id} 没有消费记录"
            total_spent = record[0]
            
            # 2. 获取所有福利商品
            cursor.execute("""
            SELECT name, price FROM commodities
            WHERE is_welfare = TRUE
            """)
            welfare_commodities = cursor.fetchall()
            
            granted = []
            for commodity in welfare_commodities:
                name, price = commodity
                
                # 3. 检查消费金额是否达到商品价格
                if total_spent >= price:
                    # 4. 检查商品是否上架
                    cursor.execute("""
                    SELECT is_active FROM plugin_status
                    WHERE plugin_name = ?
                    """, (name,))
                    status = cursor.fetchone()
                    if not status or not status[0]:
                        continue  # 跳过下架商品
                        
                    # 5. 检查是否已持有
                    cursor.execute("""
                    SELECT 1 FROM plugin_ownership
                    WHERE qq_id = ? AND plugin_name = ?
                    """, (qq_id, name))
                    if cursor.fetchone():
                        continue  # 跳过已持有商品
                        
                    # 6. 发放福利商品
                    cursor.execute("""
                    INSERT INTO plugin_ownership (qq_id, plugin_name)
                    VALUES (?, ?)
                    """, (qq_id, name))
                    granted.append(name)
            
            conn.commit()
            
            if granted:
                return True, f"已自动发放福利商品: {', '.join(granted)}"
            return True, "没有符合条件的福利商品可发放"
            
        except Exception as e:
            self.logger.error(f"自动发放福利商品失败: {e}")
            return False, f"自动发放福利商品失败: {e}"

    def __str__(self):
        return "商品存储数据库(包含购买记录、商品持有记录和商品状态)"

if __name__ == '__main__':
    store = Store()
    print(store)
