from datetime import datetime, timedelta
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from config import env
from ..sql.store_db import Store_db
from ..auth.auth import AuthManager
from ... import lssuing_cfg

class GroupService_user_API:
    """群组服务层，封装所有admin权限群组相关业务逻辑"""
    def __init__(self,websocket, message):
        self.logger = Logger("Lssuing_group_service")
        self.db = Store_db()
        self.auth = AuthManager(self.db)
        self.service = GroupService(self.db)
        self.websocket = websocket
        self.message = message
    async def handle_event(self) -> None:
        """
        统一处理各种事件
        """
        if self.message.get("message_type") != "group":
            return

        judge, msg = await self.service.list_user_permissions(self.message)
        if msg is not None:
            #await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)
            await self.service.send_at_group_msg(self.websocket, self.message.get("group_id"), self.message.get("user_id"), msg)

        judge, msg = await self.service.check_group_information(self.message)
        if msg is not None:
            await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)

        judge, msg = await self.service.help_service(self.message)
        if msg is not None:
            await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)



class GroupService:
    """2,3级权限，群组服务层，封装所有群组相关业务逻辑"""
    
    def __init__(self, db: Store_db):
        self.logger = Logger("Lssuing_group_service")
        self.db = db
        self.auth = AuthManager(db)
        self.bj_tz = pytz.timezone(lssuing_cfg.TIMEZONE)
    async def list_user_permissions(self,message) -> tuple[bool, str]:
        """
        列出群组所有的授权用户
        """
        msg = str(message.get("raw_message"))
        if not msg.startswith("list_user "): # list_user <target_group_id>
            self.logger.debug("无效的列出群组授权用户命令格式")
            return False, None
        
        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        # 检查用户权限
        check_judge, check_msg = self.auth.permission_evaluation_and_assessment(group_id, user_id, 3)
        if not check_judge:
            return False, check_msg
        
        part = msg.split(" ")
        target_group_id = part[1]

        user_list,msg_or_err = self.db.list_group_users(target_group_id)
        
        header = "\n授权用户\t等级\t父级ID"
        rows = "\n".join(f"{user}\t{level}\t{parent}" for user, level, parent in user_list)
        msg = f"{header}\n{rows}"

        if user_list:
            return True, msg
        else:
            return False, msg_or_err
    
    async def check_group_information(self, message) -> tuple[bool, str]:
        """
        检查群组信息
        """
        msg = str(message.get("raw_message"))
        if msg == "check_group": # check_group
            pass
        else:
            self.logger.debug("无效的检查群组权限命令格式")
            return False, None
        
        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        # 检查用户权限
        check_judge, check_msg = self.auth.permission_evaluation_and_assessment(group_id, user_id, 3)
        if not check_judge:
            return False, check_msg
        
        judge,msg_or_err = self.db.check_group_permission(group_id) #(2,736038975,1732373074,2025-07-13 20:21:09,2025-07-23 20:21:09,all,2025-07-13 12:21:09)
        if judge:
            msg = f"群组: {group_id}\n管理员: {msg_or_err[2]}\n创建时间: {msg_or_err[3]}\n到期时间: {msg_or_err[4]}\n群组权限: {msg_or_err[5]}"
            return True, msg
        else:
            return False, msg_or_err
    async def help_service(self, message) -> tuple[bool, str]:
        """
        指令菜单
        """
        msg = str(message.get("raw_message"))
        if msg == "help": # help_group_service
            pass
        else:
            self.logger.debug("无效的群组服务帮助命令格式")
            return False, None
        
        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        # 检查用户权限
        check_judge, check_msg = self.auth.permission_evaluation_and_assessment(group_id, user_id, 3)
        if not check_judge:
            return False, check_msg
        
        msg = "User 群组服务(group_service)指令菜单:\n" \
              "1. list_user <target_group_id> - 列出群组所有的授权用户\n" \
              "2. check_group - 检查群组信息\n"
        return True, msg

    async def send_group_message(self, websocket, group_id, message):
        """发送群消息"""
        await QQAPI_list(websocket).send_group_message(group_id, message)
    async def send_at_group_msg(self, websocket, group_id, user_id,message):
        """
        发送群聊at消息
        """
        await QQAPI_list(websocket).send_at_group_message(group_id, user_id, message)
