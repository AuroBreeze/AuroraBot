from datetime import datetime, timedelta
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from config import env
from ..sql.store_db import Store_db
from ..auth.auth import AuthManager
from ... import lssuing_cfg

class UserService_user_API:
    """群组服务层，封装所有admin权限群组相关业务逻辑"""
    def __init__(self,websocket, message):
        self.logger = Logger("Lssuing_group_service")
        self.db = Store_db()
        self.auth = AuthManager(self.db)
        self.service = UserService(self.db)
        self.websocket = websocket
        self.message = message
    async def handle_event(self) -> None:
        """
        统一处理各种事件
        """
        judge, msg = await self.service.remove_user_permission(self.message)
        if msg is not None:
            await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)
        
        judge, msg = await self.service.raise_user_permission(self.message)
        if msg is not None:
            await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)



class UserService:
    """2,3级权限，群组服务层，封装所有群组相关业务逻辑"""
    
    def __init__(self, db: Store_db):
        self.logger = Logger("Lssuing_group_service")
        self.db = db
        self.auth = AuthManager(db)
        self.bj_tz = pytz.timezone(lssuing_cfg.TIMEZONE)
    async def remove_user_permission(self, message) -> tuple[bool, str]:
        """
        移除用户权限,仅能移除本群的低一级的其他人
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("remove "): # remove <target_user_id>
            self.logger.debug("无效的移除用户权限命令格式")
            return False, None
        
        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        # 检查用户权限
        check_judge, check_msg = self.auth.permission_evaluation_and_assessment(group_id, user_id, 2)
        if not check_judge:
            return False, check_msg
        
        part = msg.split(" ")
        target_user_id = part[1]

        judge, msg_or_err = self.db.remove_user_permission(group_id, user_id, target_user_id)
        if judge:
            return True, f"成功移除用户{target_user_id}的权限"
        else:
            return False, msg_or_err
    async def raise_user_permission(self, message) -> tuple[bool, str]:
        """
        提升用户权限,仅能提升本群的低一级的其他人
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("raise "): # raise <target_user_id>
            self.logger.debug("无效的提升用户权限命令格式")
            return False, None
        
        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        # 检查用户权限
        check_judge, check_msg = self.auth.permission_evaluation_and_assessment(group_id, user_id, 2)
        if not check_judge:
            return False, check_msg
    
        part = msg.split(" ")
        target_user_id = part[1]

        judge, msg_or_err = self.auth.raise_user_permission(group_id,target_user_id,user_id)
        if judge:
            return True, f"成功提升用户{target_user_id}的权限"
        else:
            return False, msg_or_err

    async def send_group_message(self, websocket, group_id, message):
        """发送群消息"""
        await QQAPI_list(websocket).send_group_message(group_id, message)
    async def send_at_group_msg(self, websocket, group_id, user_id,message):
        """
        发送群聊at消息
        """
        await QQAPI_list(websocket).send_at_group_message(group_id, user_id, message)