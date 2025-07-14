from datetime import datetime, timedelta
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from config import env
from ..sql.store_db import Store_db
from ..auth.auth import AuthManager
from ... import lssuing_cfg

class GroupService_admin_API:
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
        # 群组授权
        judge, msg = await self.service.authorize_group(self.message) 
        if msg is not None:
            await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)
        # 取消群组授权
        judge, msg = await self.service.remove_authorization(self.message)
        if msg is not None:
            await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)

        judge, msg = await self.service.help_service(self.message)
        if msg is not None:
            await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)

        judge, msg = await self.service.check_group_list_and_kick(self.message)
        if msg is not None:
            await self.service.send_group_message(self.websocket, self.message.get("group_id"), msg)

class GroupService:
    """1级权限，群组服务层，封装所有群组相关业务逻辑"""
    
    def __init__(self, db: Store_db):
        self.logger = Logger("Lssuing_group_service")
        self.db = db
        self.auth = AuthManager(db)
        self.bj_tz = pytz.timezone(lssuing_cfg.TIMEZONE)
    async def authorize_group(self, message) -> tuple[bool, str]:
        """处理群组授权"""
        msg = str(message.get("raw_message"))
        if not msg.startswith("subscribe_group "):
            self.logger.debug("无效的群组授权格式")
            return False, None
        
        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        # 检查用户权限
        check_judge, check_msg = self.auth.permission_evaluation_and_assessment(group_id, user_id, 1)
        if not check_judge:
            return False, check_msg
        
        # 解析授权数据
        data = {}
        for line in msg.split("\n"):
            parts = line.strip().split(" ")
            if len(parts) != 2:
                continue
            data[parts[0]] = parts[1]
        
        # 验证必要参数
        required_fields = ['subscribe_group', 'starttime', 'endtime', 'user_id', 'features']
        if not all(field in data for field in required_fields):
            return False, "缺少必要的授权参数"
        
        try:
            if data['starttime'] == 'now':
                start_time = datetime.now(tz=self.bj_tz).strftime('%Y-%m-%d %H:%M:%S')
            else:
                start_time = data['starttime']
                
            end_time = datetime.now(tz=self.bj_tz) + timedelta(days=int(data['endtime']))
            
            # 创建群组权限
            if not self.db.create_group_permission(data["subscribe_group"], 
                                                 data["user_id"], 
                                                 user_id):
                self.logger.error("群组授权失败")
                return False, "群组授权失败"
            
            # 添加群组授权
            return self.db.add_group_authorization(
                data['subscribe_group'], 
                data['user_id'], 
                start_time, 
                end_time.strftime('%Y-%m-%d %H:%M:%S'), 
                data['features']
            )
            
        except ValueError as e:
            return False, f"参数格式错误: {str(e)}"
        except Exception as e:
            return False, f"授权过程中发生错误: {str(e)}"

    async def remove_authorization(self, message) -> tuple[bool, str]:
        """删除群组授权"""
        msg = str(message.get("raw_message"))
        if not msg.startswith("unsubscribe_group "):
            self.logger.debug("无效的取消授权命令格式")
            return False, None
        
        group_id = message.get("group_id")
        user_id = str(message.get("user_id"))
        
        # 检查用户权限
        check_judge, check_msg = self.auth.permission_evaluation_and_assessment(group_id, user_id, 1)
        if not check_judge:
            return False, check_msg
        
        target_group = msg.split(" ")[1]

        try:
            judge,msg = self.db.remove_authorize_group(group_id=target_group)
            if judge:
                return True, f"已取消群组 {target_group} 的授权"
            else:
                return False, f"取消群授权失败: {msg}"
        except Exception as e:
            return False, f"取消授权过程中发生错误: {str(e)}"
    async def check_group_list_and_kick(self, message) -> tuple[bool, str]:
        """
        检查群组列表并踢出不在授权列表中的群组
        
        Args:
            message: 包含消息内容的字典
            
        Returns:
            tuple[bool, str]: (操作是否成功, 结果消息)
        """
        try:
            msg = str(message.get("raw_message"))
            if msg != "check_group_list":
                self.logger.debug(f"收到无效命令: {msg}")
                return False, "无效命令，请使用'check_group_list'检查群组"

            group_id = message.get("group_id")
            user_id = str(message.get("user_id"))
            self.logger.info(f"开始检查群组列表，请求用户: {user_id}")
            
            # 检查管理员权限
            check_judge, check_msg = self.auth.permission_evaluation_and_assessment(group_id, user_id, 1)
            if not check_judge:
                self.logger.warning(f"用户 {user_id} 无权限执行此操作")
                return False, check_msg
            
            # 获取所有授权群组
            groups_list, db_error = self.db.list_group_permissions()
            if db_error:
                self.logger.error(f"数据库查询失败: {db_error}")
                return False, "获取群组列表失败，请稍后再试"
            
            if not groups_list:
                self.logger.info("当前无授权群组")
                return True, "当前无授权群组"

            # 检查并处理即将过期群组
            current_time = datetime.now(self.bj_tz)
            kicked_groups = []
            warning_groups = []
            
            for group_id, starttime, endtime in groups_list:
                try:
                    end_dt = datetime.strptime(endtime, "%Y-%m-%d %H:%M:%S").replace(tzinfo=self.bj_tz)
                    remaining_days = (end_dt - current_time).days
                    
                    if remaining_days <= 0:
                        # 已过期群组
                        await self.kick_group(group_id)
                        kicked_groups.append(f"{group_id}(已过期)")
                        self.logger.info(f"已踢出过期群组: {group_id}")
                    elif remaining_days <= 3:
                        # 即将过期群组
                        warning_groups.append(f"{group_id}(剩余{remaining_days}天)")
                except Exception as e:
                    self.logger.error(f"处理群组 {group_id} 时出错: {e}", exc_info=True)
                    continue

            # 生成结果消息
            result_msg = []
            if kicked_groups:
                result_msg.append(f"已踢出过期群组: {', '.join(kicked_groups)}")
            if warning_groups:
                result_msg.append(f"即将过期群组(3天内): {', '.join(warning_groups)}")
            if not result_msg:
                result_msg.append("当前无需要处理的群组")

            return True, "\n".join(result_msg)
            
        except Exception as e:
            self.logger.error(f"检查群组列表时发生未知错误: {e}", exc_info=True)
            return False, "系统错误，请稍后再试"
        
    async def help_service(self,message) -> tuple[bool, str]:
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
        
        msg = "Admin 群组服务(group_service)指令菜单:\n" \
              "1. subscribe_group <target_group_id>\nstarttime now\nendtime <days:int>\nuser_id <target_user_id>\nfeatures all - 添加群组授权\n" \
              "2. unsubscribe_group <target_group_id> - 取消群组授权\n" \

        return True, msg
    async def send_group_message(self, websocket, group_id, message):
        """发送群消息"""
        await QQAPI_list(websocket).send_group_message(group_id, message)
