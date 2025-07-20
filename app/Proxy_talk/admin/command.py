from datetime import datetime, timedelta
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from ..proxy_cfg import time_interval
from .. import proxy_cfg
import asyncio

from .auth import Auth

class Command_API:
    def __init__(self,websocket,message):
        self.logger = Logger(log_name='Proxy_command_api')
        self.websocket = websocket
        self.message = message
        self.api = Command()
    
    async def handle_command(self) -> tuple[bool, str]:
        check_judge,check_msg = Auth().check_msg(self.message)
        if not check_judge:
            return False, check_msg
        
        group_id = str(self.message.get('group_id'))
        excutor_id = str(self.message.get('user_id'))

        # 处理命令

        # 添加词汇
        judge,msg_or_err = await self.api.add_text(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
        
        # 发送消息
        judge,msg_or_err = await self.api.send_message(self.message,self.websocket,group_id)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
        
        # 关闭定时发送
        judge,msg_or_err = await self.api.close_message(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)

class Command:
    """
    命令处理器
    """
    def __init__(self):
        self.logger = Logger(log_name='Proxy_command')
    async def command_help(self,message:dict) -> tuple[bool, str]:
        pass

    async def add_text(self,message:dict) -> tuple[bool, str]:
        """
        添加词汇
        """

        raw_msg = str(message.get('raw_message'))
        if not raw_msg.startswith('添加词汇 '): # 添加词汇 <词汇>
            if not raw_msg.startswith('#adt '): # #adt <词汇>
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        check_judge,check_msg = Auth().check_auth(group_id,excutor_id,3) # 检查权限
        if not check_judge: # 权限不足
            return False, check_msg
        
        if not raw_msg: # 没有输入词汇
            return False, ' 消息内容为空'

        part = raw_msg.split(" ")
        if len(part) < 2 or len(part) > 3: # 词汇为空
            return False, " 参数数量错误"
        
        word = part[1]
        proxy_cfg.add_text = word
        #print(add_text)

        self.logger.info(f"添加词汇:{word},群号:{group_id},执行者:{excutor_id}")
        return True, f" 添加成功，词汇为{word}"
    async def send_message(self, message:dict,websocket, group_id):
        raw_msg = str(message.get('raw_message'))

        if raw_msg != "1":
            self.logger.debug("无效命令格式")
            return False, None
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        check_judge,check_msg = Auth().check_auth(group_id,excutor_id,3) # 检查权限
        if not check_judge: # 权限不足
            return False, check_msg

        add_text = proxy_cfg.add_text
        self.logger.info(f"发送消息:{add_text},群号:{group_id},执行者:{excutor_id}")

        # 创建发送任务
        from ..proxy_cfg import get_active_tasks
        active_tasks = get_active_tasks()
        if group_id in active_tasks and not active_tasks[group_id].done():
            return False, " 该群组已有正在运行的发送任务"

        async def send_task():
            try:
                while True:
                    check_judge,check_msg = Auth().check_cfg()
                    if not check_judge:
                        return False, check_msg
                    await QQAPI_list(websocket).send_group_message(group_id,add_text)
                    await asyncio.sleep(int(time_interval))
            except asyncio.CancelledError:
                self.logger.info(f"群组{group_id}的发送任务已取消")
                return True, " 定时发送已关闭"

        task = asyncio.create_task(send_task())
        active_tasks[group_id] = task
        task.add_done_callback(lambda _: active_tasks.pop(group_id, None))
        return True, " 定时发送已启动"
    async def close_message(self, message:dict):
        raw_msg = str(message.get('raw_message'))

        if raw_msg != "2":
            self.logger.debug("无效命令格式")
            return False, None
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        check_judge,check_msg = Auth().check_auth(group_id,excutor_id,3) # 检查权限
        if not check_judge: # 权限不足
            return False, check_msg
        

        self.logger.info(f"关闭发送消息,群号:{group_id},执行者:{excutor_id}")
        try:
            from ..proxy_cfg import get_active_tasks
            active_tasks = get_active_tasks()
            if group_id in active_tasks:
                task = active_tasks[group_id]
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                active_tasks.pop(group_id, None)
                return True, " 定时发送已关闭"
            else:
                return False, " 定时发送未启动"
        except Exception as e:
            self.logger.error(f"关闭发送消息失败,群号:{group_id},执行者:{excutor_id},错误信息:{e}")
            return False, f" 关闭发送消息失败: {e}"

