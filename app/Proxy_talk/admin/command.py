from datetime import datetime, timedelta
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
# from ..proxy_cfg import time_interval
from .. import proxy_cfg
import asyncio

from .auth import Auth
from ..sql.store_proxy import StoreProxy

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
            
        # 设置群名
        judge,msg_or_err = await self.api.set_group_name(self.message, self.websocket)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            # 如果是任务完成消息，再发送一次普通消息
            if judge and "群名修改已完成" in msg_or_err:
                await QQAPI_list(self.websocket).send_group_message(group_id, msg_or_err)

        # 帮助
        judge,msg_or_err = await self.api.command_help(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        # 添加授权QQ号
        judge,msg_or_err = await self.api.add_qq(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        # 删除授权QQ号
        judge,msg_or_err = await self.api.del_qq(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)

class Command:
    """
    命令处理器
    """
    def __init__(self):
        self.logger = Logger(log_name='Proxy_command')
    async def command_help(self,message:dict) -> tuple[bool, str]:
        """显示所有可用指令"""
        raw_msg = str(message.get('raw_message'))
        if raw_msg != '#help':
            if raw_msg != '菜单':
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        check_judge,check_msg = Auth().check_auth(group_id,excutor_id,3) # 检查权限
        if not check_judge: # 权限不足
            return False, check_msg


        help_text = """
可用指令列表:
1. 添加词汇: 
   - 格式: "添加词汇 <词汇>" 或 "#adt <词汇>"
   - 功能: 添加需要定时发送的词汇

2. 发送消息: 
   - 格式: "1"
   - 功能: 启动定时发送已添加的词汇

3. 设置发送间隔: 
   - 格式: "#interval <毫秒数>" 或 "#int <毫秒数>" 或 "添加间隔 <毫秒数>"
   - 功能: 设置定时发送的时间间隔

4. 关闭定时发送: 
   - 格式: "2"
   - 功能: 停止当前群的定时发送任务

5. 停止所有任务: 
   - 格式: "4"
   - 功能: 停止当前群的所有任务(包括定时发送和群名修改)

6. @消息发送: 
   - 格式: "[CQ:at,qq=<QQ号>] 3"
   - 功能: 定时@指定用户发送文件内容

7. 设置群名: 
   - 格式: "#stn <新群名>" 或 "设置名称 <新群名>"
   - 功能: 持续修改群名直到收到停止指令
   - 停止: 发送"6"停止修改群名

8. 等待文件: 
   - 格式: "#wf"
   - 功能: 等待用户发送文件

9. 下载文件: 
   - 在等待文件状态下发送文件链接
   - 功能: 下载并保存文件内容

10. 添加授权QQ号:
   - 格式: "#addqq <QQ号>"
   - 功能: 添加授权QQ号

11. 删除授权QQ号:
   - 格式: "#delqq <QQ号>"
   - 功能: 删除授权QQ号
"""
        return True, help_text

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
    async def send_message(self, message:dict, websocket, group_id=None):
        """发送消息命令"""
        try:
            if not group_id:
                group_id = str(message.get('group_id', ''))
            excutor_id = str(message.get('user_id', ''))

            raw_msg = str(message.get('raw_message', ''))
            if raw_msg != "1":
                self.logger.debug("无效命令格式")
                return False, None
                
            check_judge, check_msg = Auth().check_auth(group_id, excutor_id, 3)
            if not check_judge:
                return False, check_msg

            add_text = proxy_cfg.add_text
            self.logger.info(f"发送消息:{add_text},群号:{group_id},执行者:{excutor_id}")

            from ..proxy_cfg import get_active_tasks
            active_tasks = get_active_tasks()
            if group_id in active_tasks and not active_tasks[group_id].done():
                return False, "该群组已有正在运行的发送任务"

            async def send_task():
                try:
                    from ..proxy_cfg import time_interval
                    while True:
                        check_judge, check_msg = Auth().check_cfg()
                        if not check_judge:
                            return False, check_msg
                        await QQAPI_list(websocket).send_group_message(group_id, add_text)
                        await asyncio.sleep(int(time_interval) / 1000)
                except asyncio.CancelledError:
                    self.logger.info(f"群组{group_id}的发送任务已取消")
                    return True, "已结束进程"
                except Exception as e:
                    self.logger.error(f"发送消息出错: {str(e)}")
                    return False, f"发送消息时出错: {str(e)}"

            task = asyncio.create_task(send_task())
            active_tasks[group_id] = task
            task.add_done_callback(lambda _: active_tasks.pop(group_id, None))
            return True, "已启动进程"
            
        except Exception as e:
            self.logger.error(f"处理发送命令出错: {str(e)}")
            return False, f"处理命令时发生错误: {str(e)}"
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
            proxy_cfg.time_interval = int(interval)
            return True, f" 发送间隔已设置为: {interval}ms"
        except ValueError:
            return False, " 时间值必须是整数"
        except Exception as e:
            return False, f" 设置失败: {e}"

    async def wait_for_file(self, message:dict) -> tuple[bool, str]:
        """等待用户发送文件"""


        raw_msg = str(message.get('raw_message'))
        user_id = str(message.get('user_id'))
        group_id = str(message.get('group_id'))

        check_judge,check_msg = Auth().check_auth(group_id,user_id,3) # 检查权限
        if not check_judge: # 权限不足
            return False, check_msg
        
        if not raw_msg.startswith("#wf"):
            return False, None
            
        from .. import proxy_cfg
        proxy_cfg.waiting_for_file[user_id] = True
        return True, "请发送需要下载的文件"

    async def download_file(self, message:dict) -> tuple[bool, str]:
        """下载文件命令"""
        try:
            if not message or not isinstance(message, dict):
                return False, "无效的消息格式"

            msg = message.get("message")
            if not msg or not isinstance(msg, list):
                return False, None
            
            url = msg[0].get("data", {}).get("url") if msg else None
            if not url:
                return False, None

            group_id = str(message.get('group_id', ''))
            excutor_id = str(message.get('user_id', ''))

            check_judge, check_msg = Auth().check_auth(group_id, excutor_id, 3)
            if not check_judge:
                return False, check_msg

            from .. import proxy_cfg
            if excutor_id not in proxy_cfg.waiting_for_file or not proxy_cfg.waiting_for_file[excutor_id]:
                return False, None
            
            proxy_cfg.waiting_for_file[excutor_id] = False
            
            import requests
            from requests.exceptions import RequestException
            import os
            
            try:
                # 设置10秒超时
                response = requests.get(url, timeout=20)
                response.raise_for_status()
                
                # 确保目录存在
                os.makedirs('./store/file', exist_ok=True)
                
                # 保存文件
                save_path = f'./store/file/talk_{excutor_id}.txt'
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                    
                return True, f"文件已下载并保存为: {save_path}"
                
            except RequestException as e:
                self.logger.error(f"下载文件失败: {str(e)}")
                return False, f"下载失败: 网络错误({str(e)})"
            except IOError as e:
                self.logger.error(f"保存文件失败: {str(e)}")
                return False, f"保存文件失败: {str(e)}"
            except Exception as e:
                self.logger.error(f"未知错误: {str(e)}")
                return False, f"下载过程中发生未知错误"
                
        except Exception as e:
            self.logger.error(f"处理下载命令出错: {str(e)}")
            return False, f"处理命令时发生错误"

    async def close_message(self, message:dict):
        raw_msg = str(message.get('raw_message'))
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))


        check_judge,check_msg = Auth().check_auth(group_id,excutor_id,3) # 检查权限
        if not check_judge: # 权限不足
            return False, check_msg
        if raw_msg not in ["2", "4"]:
            self.logger.debug("无效命令格式")
            return False, None
            
        # 处理停止命令(4)
        if raw_msg == "4":
            group_id = str(message.get('group_id'))
            from ..proxy_cfg import get_stop_flags
            stop_flags = get_stop_flags()
            stop_flags[group_id] = True
            return True, " 已结束进程"


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
                return True, " 已结束进程"
            else:
                return False, " 发送进程未开始"
        except Exception as e:
            self.logger.error(f"关闭发送消息失败,群号:{group_id},执行者:{excutor_id},错误信息:{e}")
            return False, f" 关闭发送消息失败: {e}"
        
    async def set_group_name(self, message:dict, websocket) -> tuple[bool, str]:
        """修改群名直到收到停止指令"""
        try:
            if not message or not isinstance(message, dict):
                return False, "无效的消息格式"

            raw_msg = str(message.get('raw_message', ''))
            group_id = str(message.get('group_id', ''))
            excutor_id = str(message.get('user_id', ''))
            
            check_judge, check_msg = Auth().check_auth(group_id, excutor_id, 3)
            if not check_judge:
                return False, check_msg
            
            # 处理停止命令(6)
            if raw_msg == "6":
                from ..proxy_cfg import get_stop_flags
                stop_flags = get_stop_flags()
                stop_flags[group_id] = True
                self.logger.info(f"收到停止指令，群号:{group_id},执行者:{excutor_id}")
                return True, "已结束进程"
                
            if not raw_msg.startswith("#stn ") and not raw_msg.startswith("设置名称 "):
                return False, None
                
            new_name = raw_msg.split(" ")[1] if len(raw_msg.split(" ")) > 1 else None
            if not new_name:
                return False, "群名不能为空"
                
            from ..proxy_cfg import group_name_tasks, current_group_names, stop_flags
            if group_id in group_name_tasks and not group_name_tasks[group_id].done():
                return False, "该群组已有正在运行的群名修改任务"
                
            current_group_names[group_id] = new_name
            stop_flags[group_id] = False
            self.logger.info(f"开始修改群名:{new_name},群号:{group_id},执行者:{excutor_id}")
                
            async def name_task():
                try:
                    while True:
                        if stop_flags.get(group_id, False):
                            stop_flags.pop(group_id, None)
                            return True, "已结束进程"
                            
                        try:
                            await QQAPI_list(websocket).set_group_name(
                                group_id,
                                current_group_names[group_id]
                            )
                            await asyncio.sleep(2)
                        except Exception as e:
                            self.logger.error(f"修改群名失败: {str(e)}")
                            await asyncio.sleep(5)  # 出错后等待5秒再重试
                            
                except asyncio.CancelledError:
                    return True, "群名修改已取消"
                except Exception as e:
                    self.logger.error(f"群名修改任务出错: {str(e)}")
                    return False, f"群名修改出错: {str(e)}"
                finally:
                    current_group_names.pop(group_id, None)
                    stop_flags.pop(group_id, None)
                    
            task = asyncio.create_task(name_task())
            group_name_tasks[group_id] = task
            task.add_done_callback(lambda _: group_name_tasks.pop(group_id, None))
            return True, f"开始修改群名为: {new_name} (发送6停止)"
            
        except Exception as e:
            self.logger.error(f"处理群名修改命令出错: {str(e)}")
            return False, f"处理命令时发生错误: {str(e)}"

    async def add_qq(self, message:dict) -> tuple[bool, str]:
        """添加授权QQ号"""
        raw_msg = str(message.get('raw_message'))
        if not raw_msg.startswith('#addqq '):
            return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        try:
            qq_id = raw_msg.split()[1]
            if not qq_id.isdigit():
                return False, "QQ号必须为数字"
                
            if StoreProxy().add_qq(qq_id):
                return True, f"已成功添加授权QQ号: {qq_id}"
            return False, "添加QQ号失败"
        except IndexError:
            return False, "格式错误，应为: #addqq <QQ号>"
        except Exception as e:
            return False, f"添加QQ号出错: {str(e)}"

    async def del_qq(self, message:dict) -> tuple[bool, str]:
        """删除授权QQ号"""
        raw_msg = str(message.get('raw_message'))
        if not raw_msg.startswith('#delqq '):
            return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        try:
            qq_id = raw_msg.split()[1]
            if not qq_id.isdigit():
                return False, "QQ号必须为数字"
                
            if StoreProxy().remove_qq(qq_id):
                return True, f"已成功删除授权QQ号: {qq_id}"
            return False, "删除QQ号失败或QQ号不存在"
        except IndexError:
            return False, "格式错误，应为: #delqq <QQ号>"
        except Exception as e:
            return False, f"删除QQ号出错: {str(e)}"

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
            with open(f'./store/file/talk_{excutor_id}.txt', 'r', encoding='utf-8') as f:
                content = f.read()
                
            if not content:
                return False, " 文件内容为空"
            
            f.close() # 关闭文件
                
            # 创建发送任务
            from ..proxy_cfg import get_active_tasks
            active_tasks = get_active_tasks()
            if group_id in active_tasks and not active_tasks[group_id].done():
                return False, " 该群组已有正在运行的发送任务"

            async def send_task():
                try:
                    # 读取文件所有非空行
                    with open(f'./store/file/talk_{excutor_id}.txt', 'r', encoding='utf-8') as f:
                        lines = [line.strip() for line in f if line.strip()]
                    
                    if not lines:
                        return False, " 文件内容为空"
                        
                    current_line = 0
                    while True:
                        # 检查停止标志
                        from ..proxy_cfg import get_stop_flags,time_interval
                        stop_flags = get_stop_flags()
                        if stop_flags.get(group_id, False):
                            stop_flags.pop(group_id, None)
                            return True, " 已启动进程"
                            
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
                    return True, " 已结束进程"
                except Exception as e:
                    self.logger.error(f"发送@消息失败: {e}")
                    return False, f" 发送@消息失败: {e}"
                finally:
                    f.close() # 关闭文件

            task = asyncio.create_task(send_task())
            active_tasks[group_id] = task
            task.add_done_callback(lambda _: active_tasks.pop(group_id, None))
            return True, " 已启动进程"
            
        except FileNotFoundError:
            return False, f" 文件./store/file/talk_{excutor_id}.txt不存在"
        except Exception as e:
            return False, f" 发送@消息失败: {e}"
