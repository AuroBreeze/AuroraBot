from datetime import datetime, timedelta
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from config import env
from ..sql.store import Store
from .. import manage_cfg
from ..sql.store import Store


class AuthManager:
    """权限管理器，负责管理用户权限"""
    def __init__(self):
        self.logger = Logger("Commodity_auth_manager")
    def check_user_permission(self, executor_id: str) -> bool:
        """
        检查用户是否有指定权限
        :param qq_id: 用户QQ号
        :param permission: 权限名称
        :return: 成功与否
        """
        return manage_cfg.ADMIN_ID == str(executor_id) # 只有管理员可以管理商品

class GroupService_admin_API:
    """群组服务层，封装所有admin权限群组相关业务逻辑"""
    def __init__(self,websocket, message):
        self.logger = Logger("Commodity_admin_API")
        self.db = Store()
        self.auth = AuthManager()
        self.service = GroupService(self.db)
        self.websocket = websocket
        self.message = message
    async def handle_event(self) -> None:
        """
        统一处理各种事件
        """
        if self.message.get("message_type") != "group":
            return
        
        judge,msg_or_err = await self.service.add_commodity(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)

        judge,msg_or_err = await self.service.update_commodity(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)


class GroupService:
    """1级权限，群组服务层，封装所有群组相关业务逻辑"""
    def __init__(self, db: Store):
        self.logger = Logger("Lssuing_group_service")
        self.db = db
        self.auth = AuthManager()
        self.bj_tz = pytz.timezone(manage_cfg.TIMEZONE)
    async def add_commodity(self, message: dict) -> tuple[bool, str]:
        """
        添加商品

        :param name: 商品名称
        :param chinese_name: 中文名称
        :param price: 价格
        :param notes: 备注
        :param is_welfare: 是否是福利商品
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("add_commodity "): # add_commodity <name> <chinese_name> <price> <notes> <is_welfare>
            self.logger.debug("无效的群组授权格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        if self.auth.check_user_permission(user_id) is False:
            self.logger.warning("用户 {user_id} 权限不足, 无法添加商品")
            return False, f"用户 {user_id} 权限不足, 无法添加商品"
        
        try:
            part = msg.split(" ")
            if len(part) != 6:
                self.logger.warning("参数数量错误")
                return False, "参数数量错误"
                
            name = part[1]
            chinese_name = part[2]
            price = float(part[3])
            notes = part[4]
            is_welfare = False if part[5] == "0" else True
        except Exception as e:
            self.logger.error(f"添加商品失败, 错误信息: {e}")
        
        try:
            judge,msg_or_err = self.db.add_commodity(name, chinese_name, price, notes, is_welfare)
            return judge,msg_or_err
        except Exception as e:
            self.logger.error(f"添加商品失败, 错误信息: {e}")
            return False, f"添加商品失败,错误信息: {e}"

    async def update_commodity(self, message: dict) -> tuple[bool, str]:
        """
        更新商品信息

        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("update_commodity "): # update_commodity <name> <chinese_name> <price> <notes> <is_welfare>
            self.logger.debug("无效的更新商品格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        if self.auth.check_user_permission(user_id) is False:
            self.logger.warning(f"用户 {user_id} 权限不足, 无法更新商品")
            return False, f"用户 {user_id} 权限不足, 无法更新商品"

        try:
            part = msg.split(" ")
            if len(part) != 6:
                self.logger.warning("参数数量错误")
                return False, "参数数量错误"
                
            name = part[1]
            chinese_name = part[2]
            price = float(part[3])
            notes = part[4]
            is_welfare = False if part[5] == "0" else True

            # 调用数据库更新方法
            judge, msg_or_err = self.db.update_commodity(
                name,
                chinese_name=chinese_name,
                price=price,
                notes=notes,
                is_welfare=is_welfare
            )
            
            return judge, msg_or_err
        except ValueError as e:
            self.logger.error(f"参数格式错误: {e}")
            return False, f"参数格式错误: {e}"
        except Exception as e:
            self.logger.error(f"更新商品失败, 错误信息: {e}")
            return False, f"更新商品失败: {e}"
