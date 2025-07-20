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
        
        # 设置发送间隔
        judge,msg_or_err = await self.api.set_interval(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        # 等待文件
        judge,msg_or_err = await self.api.wait_for_file(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        # 下载文件
        judge,msg_or_err = await self.api.download_file(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        # 关闭定时发送
        judge,msg_or_err = await self.api.close_message(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        # @消息发送
        judge,msg_or_err = await self.api.at_talk(self.message, self.websocket)
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
                    await asyncio.sleep(int(time_interval) / 1000)  # 毫秒转秒
            except asyncio.CancelledError:
                self.logger.info(f"群组{group_id}的发送任务已取消")
                return True, " 定时发送已关闭"

        task = asyncio.create_task(send_task())
        active_tasks[group_id] = task
        task.add_done_callback(lambda _: active_tasks.pop(group_id, None))
        return True, " 定时发送已启动"
    async def set_interval(self, message:dict) -> tuple[bool, str]:
        """设置发送间隔(毫秒)"""
        raw_msg = str(message.get('raw_message'))
        
        if not raw_msg.startswith("#interval ") and not raw_msg.startswith("#int "): # #interval <毫秒数>
            if not raw_msg.startswith("添加间隔 "): # 添加间隔 <毫秒数>
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        check_judge,check_msg = Auth().check_auth(group_id,excutor_id,3)
        if not check_judge:
            return False, check_msg
            
        try:
            parts = raw_msg.split()
            if len(parts) < 2 or len(parts) > 2:
                return False, " 参数错误，格式应为: #interval <毫秒数>"
                
            interval = int(parts[1])
            if interval <= 0:
                return False, " 时间值必须大于0"
                
            from .. import proxy_cfg
            proxy_cfg.time_interval = interval
            return True, f" 发送间隔已设置为: {interval}ms"
        except ValueError:
            return False, " 时间值必须是整数"
        except Exception as e:
            return False, f" 设置失败: {e}"

    async def wait_for_file(self, message:dict) -> tuple[bool, str]:
        """等待用户发送文件"""
        raw_msg = str(message.get('raw_message'))
        user_id = str(message.get('user_id'))
        
        if not raw_msg.startswith("#wf"):
            return False, None
            
        from .. import proxy_cfg
        proxy_cfg.waiting_for_file[user_id] = True
        return True, "请发送需要下载的文件"

    async def download_file(self, message:dict) -> tuple[bool, str]:
        """下载文件命令"""
        msg = message.get("message")
        if msg is not None:
            url = msg[0].get("data").get("url")
        else:
            return False, None
        
        if not url:
            return False, None

        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))

        check_judge,check_msg = Auth().check_auth(group_id,excutor_id,3)
        if not check_judge:
            return False, check_msg

        from .. import proxy_cfg
        if excutor_id not in proxy_cfg.waiting_for_file or not proxy_cfg.waiting_for_file[excutor_id]:
                return False, None
        else:
            proxy_cfg.waiting_for_file[excutor_id] = False
            
        
        try:
            import requests
            import json
            import os
            
            # 读取file.json获取下载URL
                
            url = message['message'][0]['data']['url']
            if not url:
                return False, " 未找到有效的下载URL"
            
            # 下载文件
            response = requests.get(url)
            response.raise_for_status()
            
            # 保存为txt文件
            save_path = './store/file/talk.txt'
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
                
            return True, f" 文件已下载并保存为: {save_path}"
        except Exception as e:
            return False, f" 下载失败: {e}"

    async def close_message(self, message:dict):
        raw_msg = str(message.get('raw_message'))

        if raw_msg not in ["2", "4"]:
            self.logger.debug("无效命令格式")
            return False, None
            
        # 处理停止命令(4)
        if raw_msg == "4":
            group_id = str(message.get('group_id'))
            from ..proxy_cfg import get_stop_flags
            stop_flags = get_stop_flags()
            stop_flags[group_id] = True
            return True, " 已发送停止指令"
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
        
    async def at_talk(self, message:dict, websocket) -> tuple[bool, str]:
        """
        群内@他人发送txt中的消息
        """
        raw_msg = str(message.get('raw_message'))
        
        # 使用正则提取qq=后面的数字
        import re
        match = re.search(r'\[CQ:at,qq=(\d+)\] 3', raw_msg)
        if not match:
            return False, None
            
        qq_number = match.group(1)  # 提取到的QQ号
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        check_judge,check_msg = Auth().check_auth(group_id,excutor_id,3)
        if not check_judge:
            return False, check_msg
            
        try:
            # 读取文件内容
            with open('./store/file/talk.txt', 'r', encoding='utf-8') as f:
                content = f.read()
                
            if not content:
                return False, " 文件内容为空"
                
            # 创建发送任务
            from ..proxy_cfg import get_active_tasks
            active_tasks = get_active_tasks()
            if group_id in active_tasks and not active_tasks[group_id].done():
                return False, " 该群组已有正在运行的发送任务"

            async def send_task():
                try:
                    # 读取文件所有非空行
                    with open('./store/file/talk.txt', 'r', encoding='utf-8') as f:
                        lines = [line.strip() for line in f if line.strip()]
                    
                    if not lines:
                        return False, " 文件内容为空"
                        
                    current_line = 0
                    while True:
                        # 检查停止标志
                        from ..proxy_cfg import get_stop_flags
                        stop_flags = get_stop_flags()
                        if stop_flags.get(group_id, False):
                            stop_flags.pop(group_id, None)
                            return True, " @消息发送已停止"
                            
                        # 发送当前行
                        await QQAPI_list(websocket).send_at_group_message(
                            group_id,
                            qq_number,
                            " "+lines[current_line]
                        )
                        
                        # 移动到下一行，循环播放
                        current_line = (current_line + 1) % len(lines)
                        await asyncio.sleep(int(time_interval) / 1000)
                        
                except asyncio.CancelledError:
                    self.logger.info(f"群组{group_id}的@消息发送任务已取消")
                    return True, " @消息发送已关闭"
                except Exception as e:
                    self.logger.error(f"发送@消息失败: {e}")
                    return False, f" 发送@消息失败: {e}"

            task = asyncio.create_task(send_task())
            active_tasks[group_id] = task
            task.add_done_callback(lambda _: active_tasks.pop(group_id, None))
            return True, " @消息发送已启动"
            
        except FileNotFoundError:
            return False, " 文件./store/file/file.txt不存在"
        except Exception as e:
            return False, f" 发送@消息失败: {e}"
