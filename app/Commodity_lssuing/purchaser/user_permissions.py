from datetime import datetime, timedelta
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from config import env
from ..sql.store import Store
from .. import manage_cfg
from ..sql.store import Store

class UserService_user_API:
    """群组服务层，封装所有user权限群组相关业务逻辑"""
    def __init__(self,websocket, message):
        self.logger = Logger("Commodity_admin_API")
        self.db = Store()
        self.service = UserService(self.db)
        self.websocket = websocket
        self.message = message
    async def handle_event(self) -> None:
        """
        统一处理各种事件
        """
        if self.message.get("message_type") != "group":
            return
        
        judge,msg_or_err = await self.service.list_available_commodities(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)

class UserService:
    """群组服务层，封装所有群组相关业务逻辑"""
    def __init__(self, db: Store):
        self.logger = Logger("Lssuing_group_service")
        self.db = db
        self.bj_tz = pytz.timezone(manage_cfg.TIMEZONE)

    async def list_available_commodities(self, message: dict) -> tuple[bool, str]:
        """
        列出所有上架商品(用户可查看)
        
        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if msg != "list_commodities":
            self.logger.debug("无效的列出商品格式")
            return False, None

        try:
            # 获取所有上架商品
            active_plugins, err = self.db.list_plugins_state("TRUE")
            if err:
                return False, err
            
            if not active_plugins:
                return True, "当前没有上架商品"
            
            # 获取所有商品详细信息
            all_commodities, err = self.db.list_commodities()
            if err:
                return False, err
            
            # 过滤出上架商品
            active_plugin_names = {p["plugin_name"] for p in active_plugins}
            available_commodities = [
                c for c in all_commodities 
                if c["name"] in active_plugin_names
            ]
            
            # 构建响应消息
            max_name_length = max(len(str(c["name"])) for c in available_commodities) if available_commodities else 0
            max_cname_length = max(len(str(c["chinese_name"])) for c in available_commodities) if available_commodities else 0
            col_width1 = max(max_name_length, 8)  # 商品名称列宽
            col_width2 = max(max_cname_length, 10)  # 中文名称列宽
            
            response = "上架商品列表:\n"
            separator = "-" * (col_width1 + col_width2 + 20)
            response += separator + "\n"
            response += f"{'商品名称':<{col_width1}}  {'中文名称':<{col_width2}}  价格      备注\n"
            response += separator + "\n"
            
            for commodity in available_commodities:
                response += (
                    f"{commodity['name']:<{col_width1}}  "
                    f"{commodity['chinese_name']:<{col_width2}}  "
                    f"{commodity['price']:<8.2f}  "
                    f"{commodity['notes'] or '无'}\n"
                )
            
            response += separator
            
            return True, response
        except Exception as e:
            self.logger.error(f"列出上架商品失败: {e}")
            return False, f"列出上架商品失败: {e}"
