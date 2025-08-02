# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
# from ..proxy_cfg import time_interval
# from .. import proxy_cfg
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
        # 处理好友请求
        judge,msg_or_err = await self.api.approve_friend_add(self.message,self.websocket)
        judge,msg_or_err = await self.api.approve_invite_group(self.message,self.websocket)

        group_id = str(self.message.get('group_id'))
        excutor_id = str(self.message.get('user_id'))


        check_judge,check_msg = Auth().check_msg(self.message)
        if not check_judge:
            return False, check_msg
        
        judge,msg_or_err = await self.api.add_text(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_group_message_array(group_id,msg_or_err)
        
        judge,msg_or_err = await self.api.send_message(self.message,self.websocket,group_id)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
        
        judge,msg_or_err = await self.api.set_interval(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        judge,msg_or_err = await self.api.wait_for_file(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        judge,msg_or_err = await self.api.download_file(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        judge,msg_or_err = await self.api.close_message(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        judge,msg_or_err = await self.api.at_talk(self.message, self.websocket)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        judge,msg_or_err = await self.api.set_group_name(self.message, self.websocket)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
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
            
        # 列出授权QQ号
        judge,msg_or_err = await self.api.list_auth_members(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        # 清空下载的文件
        judge,msg_or_err = await self.api.clear_downloaded_files(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        # 清空添加的词汇
        judge,msg_or_err = await self.api.clear_added_texts(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)

        # 响应
        judge,msg_or_err = await self.api.response(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)

        # 列出群组
        judge,msg_or_err = await self.api.list_groups(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
        # 添加群组
        judge,msg_or_err = await self.api.add_group(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
        # 删除群组
        judge,msg_or_err = await self.api.remove_group(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)

        # 退出所有非白名单群组
        judge,msg_or_err = await self.api.exit_non_whitelist_groups(self.message, self.websocket)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)

        # 修改群名片
        judge,msg_or_err = await self.api.set_group_card(self.message,self.websocket)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        # 等待头像上传
        judge,msg_or_err = await self.api.wait_for_avatar(self.message)
        if msg_or_err is not None:
            await QQAPI_list(self.websocket).send_at_group_message(group_id,excutor_id,msg_or_err)
            
        # 设置头像
        judge,msg_or_err = await self.api.set_avatar(self.message,self.websocket)
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
        71の                                                                                                                  
  ┌── 1. 添加词汇 <词汇>              
  ├── 2. 发送消息: 1                     
  ├── 3. 添加间隔 <毫秒数>                 
  ├── 4. 关闭发送: 2             
  ├── 5. 停止所有: 4         
  ├── 6*. 全局停止: 停止/0            
  ├── 7*. @at 3                   
  ├── 8*. 设置名称 <新群名>              
  ├── 9*. 添加文件                      
  ├── 10*.下载文件                   
  ├── 11*.授权 <QQ号>                         
  ├── 12*.取消授权 <QQ号>                      
  ├── 13*.列出授权                         
  ├── 14*.清空文件                         
  ├── 15*.清空词汇
  ├── 16*.添加白名单群组                          
  ├── 17*.移除白名单群组 <群号>        
  ├── 18*.列出白名单群组                  
  ├── 19*.退群                        
  ├── 20*.更换头像                              
  └── 21*.更改名字 <名称>                                                                                 
"""
        return True, help_text

    async def add_text(self, message:dict) -> tuple[bool, str]:
        """
        添加词汇和图片，保留原始顺序
        """
        raw_msg = str(message.get('raw_message'))
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
        
        # 检查权限
        check_judge, check_msg = Auth().check_auth(group_id, excutor_id, 3)
        if not check_judge:
            return False, check_msg

        # 处理文本命令
        if raw_msg.startswith('添加词汇 ') or raw_msg.startswith('#adt '):
            pass
        else:
            return False, None

        # 处理混合消息
        if 'message' in message and isinstance(message['message'], list):
            import os
            import requests
            import base64
            from datetime import datetime
            
            # 创建存储目录
            os.makedirs('./store/file/images', exist_ok=True)
            
            if str(message["message"][0]["data"]["text"][:4]) == '添加词汇':
                message["message"][0]["data"]["text"] = message["message"][0]["data"]["text"][5:]
            
            
            combined_msg = []
            for item in message['message']:
                if item['type'] == 'text':
                    text = item['data']['text'].strip()
                    if text:
                        combined_msg.append({
                            'type': 'text',
                            'data': {'text': text},
                        })
                elif item['type'] == 'image':
                    try:
                        url = item['data']['url']
                        filename = item['data']['file']
                        
                        # 直接下载图片并转换为base64，避免先写入文件再读取
                        response = requests.get(url, timeout=10)
                        base64_data = base64.b64encode(response.content).decode('utf-8')
                            
                        combined_msg.append({
                            'type': 'image',
                            'data': {
                                "file": f"base64://{base64_data}",
                                "summary": "[图片]"
                            }
                        })
                    except Exception as e:
                        self.logger.error(f"下载图片失败: {str(e)}")
                        continue
            
            if combined_msg:
                combined_msg_copy = combined_msg.copy()
                from .. import proxy_cfg
                proxy_cfg.add_text = combined_msg
                self.logger.info(f"添加组合消息(保留顺序),群号:{group_id},执行者:{excutor_id}")

                combined_msg_copy.append({"type": "text", "data": {"text": "\n添加成功"}})

                return True, combined_msg_copy
        
        return False, None
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
            
            from .. import proxy_cfg

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
                        await QQAPI_list(websocket).send_group_message_array(group_id, add_text)
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
        
        if raw_msg != "#wf":
            if raw_msg != "添加文件":
                return False, None
            
        from .. import proxy_cfg
        # 检查是否已经在等待头像
        if proxy_cfg.waiting_for_avatar.get(user_id, False):
            return False, "您当前正在等待设置头像，请先完成或取消该操作"
            
        proxy_cfg.waiting_for_file[user_id] = True
        proxy_cfg.waiting_for_avatar.pop(user_id, None)  # 确保取消任何等待头像状态
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
            # 检查是否是发起命令的用户
            if excutor_id not in proxy_cfg.waiting_for_file or not proxy_cfg.waiting_for_file[excutor_id]:
                return False, None
            
            # 清除等待状态
            proxy_cfg.waiting_for_file[excutor_id] = False
            # 确保只有发起者可以上传
            if str(message.get('user_id')) != excutor_id:
                return False, "只有发起命令的用户可以上传文件"
            
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
                    
                return True, f"文本添加成功"
                
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
        if raw_msg not in ["2", "4", "停止", "0"]:
            self.logger.debug("无效命令格式")
            return False, None
            
        # 处理停止命令(4)
        if raw_msg == "4":
            group_id = str(message.get('group_id'))
            from ..proxy_cfg import get_stop_flags
            stop_flags = get_stop_flags()
            stop_flags[group_id] = True
            return True, " 已结束进程"
            
        # 处理全局停止命令(0)
        if raw_msg == "停止" or raw_msg == "0":
            from .. import proxy_cfg
            if excutor_id != proxy_cfg.ADMIN_ID:
                return False, " 只有管理员可以使用全局停止功能"
                
            from ..proxy_cfg import get_active_tasks, get_stop_flags
            active_tasks = get_active_tasks()
            stop_flags = get_stop_flags()
            
            # 停止所有群组的发送任务
            for group_id in list(active_tasks.keys()):
                task = active_tasks[group_id]
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                active_tasks.pop(group_id, None)
                
            return True, " 已停止所有群组的发送任务"


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
        if not raw_msg.startswith('#addqq '): # #addqq <QQ号>
            if not raw_msg.startswith("授权 "): # 授权 <QQ号>
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))

        from .. import proxy_cfg
            
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        try:
            qq_id = raw_msg.split()[1]
            if not qq_id.isdigit():
                return False, "QQ号必须为数字"
                
            if StoreProxy().add_qq(qq_id):
                return True, f"已成功添加授权QQ号: {qq_id}"
            return False, "授权QQ号失败"
        except IndexError:
            return False, "格式错误，应为: #addqq <QQ号>"
        except Exception as e:
            return False, f"授权QQ号出错: {str(e)}"

    async def del_qq(self, message:dict) -> tuple[bool, str]:
        """删除授权QQ号"""
        raw_msg = str(message.get('raw_message'))
        if not raw_msg.startswith('#delqq '): # #delqq <QQ号>
            if not raw_msg.startswith("取消授权 "): # 取消授权 <QQ号>
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        from .. import proxy_cfg
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        try:
            qq_id = raw_msg.split()[1]
            if not qq_id.isdigit():
                return False, "QQ号必须为数字"
                
            if StoreProxy().remove_qq(qq_id):
                return True, f"已成功取消授权QQ号: {qq_id}"
            return False, "取消授权QQ号失败或QQ号不存在"
        except IndexError:
            return False, "格式错误，应为: #delqq <QQ号>"
        except Exception as e:
            return False, f"取消授权QQ号出错: {str(e)}"

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

        from ..proxy_cfg import ADMIN_ID
        if qq_number == ADMIN_ID:
            return False, " 不许大逆不道你71爷爷"
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        check_judge,check_msg = Auth().check_auth(group_id,excutor_id,3)
        if not check_judge:
            return False, check_msg
            
        try:
            # 缓存文件内容，避免重复读取
            file_path = f'./store/file/talk_{excutor_id}.txt'
            file_content = None
            
            # 尝试从缓存获取文件内容（如果有缓存机制的话）
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
            except FileNotFoundError:
                try:
                    with open("./store/file/talk_template.txt", 'r', encoding='utf-8') as f:
                        file_content = f.read()
                except FileNotFoundError:
                    self.logger.error("模板文件不存在")
                    return False, "模板文件不存在"
                
            if not file_content:
                return False, " 文件内容为空"
            
            # 创建发送任务
            from ..proxy_cfg import get_active_tasks, get_stop_flags
            active_tasks = get_active_tasks()
            stop_flags = get_stop_flags()
            
            # 清除该群组的停止标志
            stop_flags.pop(group_id, None)
            
            if group_id in active_tasks and not active_tasks[group_id].done():
                return False, " 该群组已有正在运行的发送任务"

            async def send_task():
                try:
                    # 直接使用已读取的文件内容，避免重复读取文件
                    lines = [line.strip() for line in file_content.split('\n') if line.strip()]
                    
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

            task = asyncio.create_task(send_task())
            active_tasks[group_id] = task
            task.add_done_callback(lambda _: active_tasks.pop(group_id, None))
            return True, " 已启动进程"
            
        except Exception as e:
            return False, f" 发送@消息失败: {e}"
    
    async def approve_other_join_group(self, websocket, message:dict) -> tuple[bool, str]:
        """
        审批其他人加入群
        """

        try:
            user_id = message.get("user_id")
            if message.get("post_type") == "request" and message.get("request_type") == "group":
                if message.get("sub_type") == "add":
                    flag = message.get("flag")
                    approve = True
                
                    await QQAPI_list(websocket).set_group_add_request(flag, approve)
                    return True, "已同意用户 {} 加入群聊".format(user_id)

            return False, None #"已拒绝或忽略 用户{user_id}请求".format(user_id=user_id)
        except Exception as e:
            return False, f"审批其他人加入群出错: {str(e)}"
    async def list_auth_members(self, message:dict) -> tuple[bool, str]:
        """
        列出授权成员
        """
        raw_msg = str(message.get('raw_message'))
        if raw_msg != '#listqq':
            if raw_msg != "列出授权":
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))

        from .. import proxy_cfg
            
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        auth_list = StoreProxy().list_all()
        if not auth_list:
            return True, "当前没有授权用户"
            
        auth_text = "授权用户列表:\n" + "\n".join(f"{i+1}. {qq}" for i, qq in enumerate(auth_list))
        return True, auth_text

    async def clear_downloaded_files(self, message:dict) -> tuple[bool, str]:
        """清空下载的文件"""
        raw_msg = str(message.get('raw_message'))
        if raw_msg != '清空文件':
            if raw_msg != "#cf":
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))

        from .. import proxy_cfg
            
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        import os
        import glob
        try:
            files = glob.glob('./store/file/*.txt')
            for f in files:
                os.remove(f)
            return True, " 文本已清空"
        except Exception as e:
            return False, f" 清空文件失败: {str(e)}"

    async def clear_added_texts(self, message:dict) -> tuple[bool, str]:
        """清空添加的词汇"""
        raw_msg = str(message.get('raw_message'))
        if raw_msg != '清空词汇':
            if raw_msg != "#ct":
                return False, None

            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))

        
        from .. import proxy_cfg
            
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        try:
            from .. import proxy_cfg
            proxy_cfg.add_text = ""
            return True, " 词汇已清空"
        except Exception as e:
            return False, f" 清空词汇失败: {str(e)}"

    async def add_group(self, message:dict) -> tuple[bool, str]:
        """添加白名单群组"""
        raw_msg = str(message.get('raw_message'))
        if not raw_msg.startswith('#addgroup '):
            if not raw_msg.startswith("添加白名单群组 "):
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        from .. import proxy_cfg
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        try:
            target_group = raw_msg.split()[1]
            if not target_group.isdigit():
                return False, " 群号必须为数字"
                
            if StoreProxy().add_group(target_group):
                return True, f" 已添加白名单群组: {target_group}"
            return False, " 添加白名单群组失败"
        except IndexError:
            return False, " 格式错误，应为: #addgroup <群号>"
        except Exception as e:
            return False, f" 添加白名单群组出错: {str(e)}"

    async def remove_group(self, message:dict) -> tuple[bool, str]:
        """移除白名单群组"""
        raw_msg = str(message.get('raw_message'))
        if not raw_msg.startswith('#delgroup '):
            if not raw_msg.startswith("移除白名单群组 "):
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        from .. import proxy_cfg
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        try:
            target_group = raw_msg.split()[1]
            if not target_group.isdigit():
                return False, " 群号必须为数字"
                
            if StoreProxy().remove_group(target_group):
                return True, f" 已移除白名单群组: {target_group}"
            return False, " 移除白名单群组失败或群组不存在"
        except IndexError:
            return False, " 格式错误，应为: #delgroup <群号>"
        except Exception as e:
            return False, f" 移除白名单群组出错: {str(e)}"

    async def list_groups(self, message:dict) -> tuple[bool, str]:
        """列出所有白名单群组"""
        raw_msg = str(message.get('raw_message'))
        if raw_msg != '#listgroups':
            if raw_msg != "列出白名单群组":
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        from .. import proxy_cfg
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        groups = StoreProxy().list_groups()
        if not groups:
            return True, " 当前没有白名单群组"
            
        groups_text = " 白名单群组列表:\n" + "\n".join(f"{i+1}. {group}" for i, group in enumerate(groups))
        return True, groups_text

    async def exit_non_whitelist_groups(self, message:dict, websocket) -> tuple[bool, str]:
        """退出所有不在白名单中的群组"""
        raw_msg = str(message.get('raw_message'))
        if raw_msg != '#exitgroups':
            if raw_msg != "退群":
                return False, None
            
        group_id = str(message.get('group_id'))
        excutor_id = str(message.get('user_id'))
            
        from .. import proxy_cfg
        if excutor_id != proxy_cfg.ADMIN_ID:
            return False, None
            
        try:
            # 获取白名单群组
            whitelist = set(StoreProxy().list_groups())
            
            # 获取当前加入的所有群组
            api = QQAPI_list(websocket)
            all_groups = await api.get_group_list()
            #print(all_groups)
            if not all_groups:
                return False, " 获取群组列表失败"
            
            # 找出不在白名单中的群组
            non_whitelist = [g for g in all_groups if g not in whitelist]
            
            if not non_whitelist:
                return True, " 当前没有需要退出的非白名单群组"
                
            # 退出这些群组
            for group in non_whitelist:
                await api.set_group_leave(group)
                
            return True, f" 已退出以下非白名单群组: {', '.join(non_whitelist)}"
            
        except Exception as e:
            return False, f" 退出非白名单群组失败: {str(e)}"
    async def response(self, message:dict) -> tuple[bool, str]:
        """响应"""
        raw_msg = str(message.get('raw_message'))
        if raw_msg != '71':
            return False, None
        
        return True, " 主人我在"
    
    async def approve_friend_add(self, message:dict, websocket) -> tuple[bool, str]:
        """
        审批好友请求
        """
        try:
            user_id = message.get("user_id")
            if message.get("post_type") == "request" and message.get("request_type") == "friend":
                
                flag = message.get("flag")
                approve = True
                await QQAPI_list(websocket).set_friend_add_request(flag, approve)
                return True, "已同意用户 {} 成为好友".format(user_id)

            return False, None #"已拒绝或忽略 用户{user_id}请求".format(user_id=user_id)
        except Exception as e:
            self.logger.error(f"审批好友请求出错: {str(e)}")
            return False, f"审批好友请求出错: {str(e)}"
        
    async def set_group_card(self, message:dict, websocket) -> tuple[bool, str]:
        """
        设置群名片
        """
        try:
            raw_msg = str(message.get('raw_message'))
            if not raw_msg.startswith('更改名字 '):
                return False, None
            
            group_id = str(message.get('group_id'))
            excutor_id = str(message.get('user_id'))

            check_judge,check_msg = Auth().check_auth(group_id,excutor_id,2)
            if not check_judge:
                return False, None
            
            card_name = raw_msg.split()[1]
            self_id = str(message.get('self_id'))
            check_judge = await QQAPI_list(websocket).set_group_card(group_id,self_id ,card_name)

            if check_judge:
                return True, f" 改名成功，当前名字为: {card_name}"
            else:
                return False, f" 更改群名片出错: {check_msg}"
        except Exception as e:
            self.logger.error(f" 设置群名片出错: {str(e)}")
            return False, f" 设置群名片出错: {str(e)}"
        
    async def wait_for_avatar(self, message:dict) -> tuple[bool, str]:
        """等待用户上传头像图片"""
        raw_msg = str(message.get('raw_message'))
        user_id = str(message.get('user_id'))
        group_id = str(message.get('group_id'))

        check_judge,check_msg = Auth().check_auth(group_id,user_id,3)
        if not check_judge:
            return False, check_msg
        
        if raw_msg != "#avatar":
            if raw_msg != "更换头像":
                return False, None
            
        from .. import proxy_cfg
        # 检查是否已经在等待文件
        if proxy_cfg.waiting_for_file.get(user_id, False):
            return False, "您当前正在等待上传文件，请先完成或取消该操作"
            
        proxy_cfg.waiting_for_avatar[user_id] = True
        proxy_cfg.waiting_for_file.pop(user_id, None)  # 确保取消任何等待文件状态
        return True, "请发送需要设置为头像的图片"

    async def set_avatar(self, message:dict, websocket) -> tuple[bool, str]:
        """
        设置头像
        """
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
            # 检查是否是发起命令的用户
            if excutor_id not in proxy_cfg.waiting_for_avatar or not proxy_cfg.waiting_for_avatar[excutor_id]:
                return False, None
            
            # 清除等待状态
            proxy_cfg.waiting_for_avatar[excutor_id] = False
            # 确保只有发起者可以上传
            if str(message.get('user_id')) != excutor_id:
                return False, "只有发起命令的用户可以上传头像"
            
            import requests
            from requests.exceptions import RequestException
            import os
            import tempfile
            
            try:
                response = requests.get(url, timeout=20)
                response.raise_for_status()
                
                # 创建临时文件保存图片
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                    tmp_file.write(response.content)
                    tmp_path = tmp_file.name
                
                # 设置头像
                check_judge = await QQAPI_list(websocket).set_self_avatar(tmp_path)
                
                # 删除临时文件
                os.unlink(tmp_path)
                
                if check_judge:
                    return True, "头像已更新"
                return False, "设置头像失败"
                
            except RequestException as e:
                self.logger.error(f"下载头像失败: {str(e)}")
                return False, f"下载头像失败: {str(e)}"
            except Exception as e:
                self.logger.error(f"设置头像失败: {str(e)}")
                return False, f"设置头像失败: {str(e)}"
        except Exception as e:
            self.logger.error(f"处理头像设置出错: {str(e)}")
            return False, f"处理头像设置出错: {str(e)}"
    async def approve_invite_group(self, message:dict, websocket) -> tuple[bool, str]:
        """
        审批加群请求
        """
        """处理消息，检查是否为群邀请事件"""
        try:
            # 只处理群邀请请求
            if (message.get("post_type") == "request" and
                    message.get("request_type") == "group" and
                    message.get("sub_type") == "invite"):
                pass
            else:
                return False, None
        except Exception as e:
            self.logger.error(f"处理消息时出错: {e}")
            return False,None
        
        try:
            group_id = message.get("group_id")
            user_id = str(message.get("user_id"))
            comment = message.get("comment", "")
            flag = message.get("flag")

            self.logger.info(f"收到群邀请: 群号={group_id}, 邀请人={user_id}, 理由={comment}")

            admin_qq_list = StoreProxy().list_all()
            
            from .. import proxy_cfg
            admin_qq_list.append(str(proxy_cfg.ADMIN_ID))

            # 检查邀请人是否为管理员
            if user_id in admin_qq_list:
                self.logger.info(f"管理员 {user_id} 邀请加群 {group_id}，自动同意")
                await QQAPI_list(websocket).set_group_add_request(flag, True)
            else:
                self.logger.info(f"非管理员 {user_id} 邀请加群 {group_id}，自动拒绝")
                await QQAPI_list(websocket).set_group_add_request(flag, False)

            self.logger.info(f"已处理群邀请: 群号={group_id}, 邀请人={user_id}, 理由={comment}")
            return True, None
        except Exception as e:
            self.logger.error(f"处理群邀请时出错: {e}")