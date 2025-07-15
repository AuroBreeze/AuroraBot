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

    async def update_plugin_status(self, message: dict) -> tuple[bool, str]:
        """
        更新插件上架状态
        
        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("update_status "): # update_status <plugin_id> <status>
            self.logger.debug("无效的更新状态格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        if self.auth.check_user_permission(user_id) is False:
            self.logger.warning(f"用户 {user_id} 权限不足, 无法更新插件状态")
            return False, f"用户 {user_id} 权限不足, 无法更新插件状态"

        try:
            parts = msg.split(" ")
            if len(parts) != 3:
                return False, "参数错误，格式应为: update_status <插件ID> <1/0>"
            
            plugin_id = parts[1]
            try:
                status = int(parts[2])
                if status not in (0, 1):
                    return False, "状态参数错误，应为0(下架)或1(上架)"
            except ValueError:
                return False, "状态参数错误，应为0(下架)或1(上架)"
            
            # 调用数据库方法更新状态
            success, msg_or_err = self.db.update_plugin_status(plugin_id, bool(status))
            return success, msg_or_err
            
        except Exception as e:
            self.logger.error(f"更新插件状态失败: {e}")
            return False, f"更新插件状态失败: {e}"

    async def list_commodities_with_status(self, message: dict) -> tuple[bool, str]:
        """
        列出所有插件及其上架状态
        
        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if msg != "list_commodities_status":
            self.logger.debug("无效的列出商品格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        if self.auth.check_user_permission(user_id) is False:
            self.logger.warning(f"用户 {user_id} 权限不足, 无法查看商品列表")
            return False, f"用户 {user_id} 权限不足, 无法查看商品列表"

        try:
            # 获取所有商品
            commodities, err = self.db.list_commodities()
            if err:
                return False, err
            
            if not commodities:
                return True, "当前没有商品"
            
            # 获取所有上架插件
            active_plugins, err = self.db.list_plugins_state("TRUE")
            inactive_plugins, errs = self.db.list_plugins_state("FALSE")
            if err:
                return False, err
            
            
            # 构建插件状态字典
            active_plugin_names = {p["plugin_name"] for p in active_plugins}
            
            # 构建响应消息
            max_id_length = max(len(str(c["name"])) for c in commodities) if commodities else 0
            col_width = max(max_id_length, 8)  # 至少8个字符宽度
            
            response = "商品状态列表:\n"
            separator = "-" * (col_width + 10)
            response += separator + "\n"
            response += f"{'商品名称':<{col_width}}上架状态\n"
            response += separator + "\n"
            
            for commodity in commodities:
                status = "1" if commodity["name"] in active_plugin_names else "0"
                response += f"{commodity['name']:<{col_width}}   {status}\n"
            
            response += separator
            
            return True, response
        except Exception as e:
            self.logger.error(f"列出商品状态失败: {e}")
            return False, f"列出商品状态失败: {e}"

    async def add_plugin_ownership(self, message: dict) -> tuple[bool, str]:
        """
        为用户添加商品持有记录
        
        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("add_ownership "): # add_ownership <qq_id> <plugin_name>
            self.logger.debug("无效的添加持有记录格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        if self.auth.check_user_permission(user_id) is False:
            self.logger.warning(f"用户 {user_id} 权限不足, 无法添加持有记录")
            return False, f"用户 {user_id} 权限不足, 无法添加持有记录"

        try:
            parts = msg.split(" ")
            if len(parts) != 3:
                return False, "参数错误，格式应为: add_ownership [QQ号] [插件名称]"
            
            target_qq = parts[1]
            plugin_name = parts[2]
            
            # 调用数据库添加持有记录
            success, msg_or_err = self.db.add_plugin_ownership(target_qq, plugin_name)
            return success, msg_or_err
            
        except Exception as e:
            self.logger.error(f"添加持有记录失败: {e}")
            return False, f"添加持有记录失败: {e}"

    async def get_user_info(self, message: dict) -> tuple[bool, str]:
        """
        获取用户信息(消费金额和插件持有情况)
        
        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("user_info "):
            self.logger.debug("无效的用户信息查询格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        if self.auth.check_user_permission(user_id) is False:
            self.logger.warning(f"用户 {user_id} 权限不足, 无法查询用户信息")
            return False, f"用户 {user_id} 权限不足, 无法查询用户信息"

        try:
            parts = msg.split(" ")
            if len(parts) != 2:
                return False, "参数错误，格式应为: user_info [QQ号]"
            
            target_qq = parts[1]
            user_info, err = self.db.list_user_info(target_qq)
            if err:
                return False, err
            
            if not user_info:
                return True, f"用户 {target_qq} 暂无消费记录和插件持有信息"
            
            # 构建响应消息
            response = f"用户 {target_qq} 信息:\n"
            response += f"总消费金额: ¥{user_info['total_spent']:.2f}\n"
            response += f"持有插件数: {len(user_info['plugins'])}\n"
            
            if user_info["latest_purchase"]:
                response += f"最近消费时间: {user_info['latest_purchase']}\n"
            
            if user_info["plugins"]:
                response += "\n插件列表:\n"
                separator = "-" * 50
                response += separator + "\n"
                response += f"{'插件名称':<15} {'中文名':<15} {'价格':<8} {'备注'}\n"
                response += separator + "\n"
                
                for plugin in user_info["plugins"]:
                    response += (
                        f"{plugin['name']:<15} "
                        f"{plugin['chinese_name']:<15} "
                        f"¥{plugin['price']:<7.2f} "
                        f"{plugin['notes'] or '无'}\n"
                    )
                
                response += separator
            
            return True, response
        except Exception as e:
            self.logger.error(f"获取用户信息失败: {e}")
            return False, f"获取用户信息失败: {e}"
    async def delete_commodity(self, message: dict) -> tuple[bool, str]:
        """
        删除商品
        
        :param message: 消息字典
        :return: 成功与否，错误信息
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("delete_commodity "):  # delete_commodity <name>
            self.logger.debug("无效的删除商品格式")
            return False, None

        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        if self.auth.check_user_permission(user_id) is False:
            self.logger.warning(f"用户 {user_id} 权限不足, 无法删除商品")
            return False, f"用户 {user_id} 权限不足, 无法删除商品"

        try:
            parts = msg.split(" ")
            if len(parts) != 2:
                return False, "参数错误，格式应为: delete_commodity <商品名称>"
            
            name = parts[1]
            success, msg_or_err = self.db.delete_commodity(name)
            return success, msg_or_err
            
        except Exception as e:
            self.logger.error(f"删除商品失败: {e}")
            return False, f"删除商品失败: {e}"

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

        judge,msg_or_err = await self.service.list_commodities_with_status(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)

        judge,msg_or_err = await self.service.update_plugin_status(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)
        
        judge,msg_or_err = await self.service.add_plugin_ownership(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)
        
        judge,msg_or_err = await self.service.get_user_info(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)

        judge,msg_or_err = await self.service.delete_commodity(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message(self.message.get("group_id"), msg_or_err)

