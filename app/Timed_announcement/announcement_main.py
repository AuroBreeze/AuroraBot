import json
import asyncio
from datetime import datetime
import pytz
from api.Logger_owner import Logger
from api.Botapi import QQAPI_list
from config import env
from .sql.store_announcement import StoreAnnouncement
from app.Lssuing.services.sql.store_db import Store_db
from app.Lssuing.services.auth.auth import AuthManager

class TimedAnnouncement:
    """
    定时喊话插件主类
    """
    def __init__(self, websocket, message: dict):
        self.logger = Logger("TimedAnnouncement")
        self.bj_tz = pytz.timezone(env.TIMEZONE)
        self.websocket = websocket
        self.message = message
        self.db = StoreAnnouncement()
        self.auth_db = Store_db()
        self.auth = AuthManager(self.auth_db)
        
    async def handle_event(self):
        """
        处理消息事件
        """
        if self.message.get("message_type") != "group":
            return
            
        msg = self.message.get("raw_message", "").strip()
        if not msg:
            return
            
        user_id = str(self.message.get("user_id"))
        group_id = str(self.message.get("group_id"))
        
        # 解析命令
        if msg.startswith("定时喊话"):
            # 检查用户权限（需要3级权限）
            if not self.auth.check_permission(group_id, user_id, 3):
                await self.send_message("⚠️ 您没有权限使用定时喊话功能")
                return
            await self.handle_announcement_command(msg, user_id, group_id)
        elif msg == "喊话帮助" or msg == "喊话菜单":
            # 检查用户权限（需要3级权限）
            if not self.auth.check_permission(group_id, user_id, 3):
                await self.send_message("⚠️ 您没有权限使用定时喊话功能")
                return
            await self.show_help()
        else:
            # 不是定时喊话命令，不处理
            pass
            
    async def handle_announcement_command(self, msg: str, user_id: str, group_id: str):
        """
        处理定时喊话命令
        """
        parts = msg.split()
        
        if len(parts) < 2:
            await self.show_help()
            return
            
        command = parts[1]
        
        if command == "添加":
            await self.add_announcement(parts, user_id, group_id)
        elif command == "删除":
            await self.delete_announcement(parts, user_id)
        elif command == "清除":
            await self.clear_all_announcements(user_id, group_id)
        elif command == "确认清除":
            await self.confirm_clear_all(user_id, group_id)
        elif command == "列表":
            await self.list_announcements(user_id, group_id)
        elif command == "启用":
            await self.toggle_announcement(parts, user_id, True)
        elif command == "禁用":
            await self.toggle_announcement(parts, user_id, False)
        elif command == "帮助":
            await self.show_help()
        else:
            await self.send_message("❌ 未知命令，请输入'喊话帮助'查看使用说明")
            
    async def add_announcement(self, parts: list, user_id: str, group_id: str):
        """
        添加定时喊话任务
        格式：定时喊话 添加 时间 消息 [星期] [atall]
        时间格式：HH:MM (24小时制)
        星期格式：1-7 (1=周一，7=周日)，多个用逗号分隔，默认每天
        atall参数：可选，在消息后加上"atall"表示@全体成员
        """
        if len(parts) < 4:
            await self.send_message("❌ 格式错误\n正确格式：定时喊话 添加 HH:MM 消息内容 [星期] [atall]\n例如：定时喊话 添加 08:30 早上好 1,2,3,4,5 atall")
            return
            
        # 解析时间
        time_str = parts[2]
        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            await self.send_message("❌ 时间格式错误，请使用 HH:MM 格式\n例如：08:30")
            return
            
        # 解析消息和参数
        message_parts = parts[3:]
        message = ""
        days_of_week = [1, 2, 3, 4, 5, 6, 7]  # 默认每天
        at_all = False  # 是否@全体成员
        
        # 解析参数
        i = 0
        while i < len(message_parts):
            part = message_parts[i]
            
            # 检查是否是星期参数（数字和逗号组成）
            if all(c.isdigit() or c == ',' for c in part):
                try:
                    days_of_week = [int(day.strip()) for day in part.split(",") if day.strip()]
                    if not all(1 <= day <= 7 for day in days_of_week):
                        await self.send_message("❌ 星期参数错误，请输入1-7的数字，用逗号分隔\n1=周一，2=周二，...，7=周日")
                        return
                    i += 1
                    continue
                except ValueError:
                    # 不是星期参数，继续检查
                    pass
            
            # 检查是否是atall参数
            if part.lower() == "atall":
                at_all = True
                i += 1
                continue
            
            # 否则是消息内容的一部分
            if message:
                message += " " + part
            else:
                message = part
            i += 1
        
        if not message:
            await self.send_message("❌ 消息内容不能为空")
            return
        
        # 添加任务（将at_all信息存储在消息中，使用特殊标记）
        # 格式：[atall]消息内容 或 普通消息内容
        stored_message = f"[atall]{message}" if at_all else message
        
        success, result_msg = self.db.add_announcement(
            group_id, user_id, stored_message, hour, minute, days_of_week
        )
        
        if success:
            days_str = self._format_days_of_week(days_of_week)
            at_all_str = "✅ @全体成员" if at_all else "❌ 不@全体成员"
            await self.send_message(
                f"✅ 定时喊话任务添加成功！\n"
                f"📅 时间：{hour:02d}:{minute:02d}\n"
                f"📝 内容：{message}\n"
                f"📆 星期：{days_str}\n"
                f"🔔 {at_all_str}\n"
                f"🆔 任务ID：{result_msg.split('ID: ')[1]}"
            )
        else:
            await self.send_message(f"❌ {result_msg}")
            
    async def delete_announcement(self, parts: list, user_id: str):
        """
        删除定时喊话任务
        格式：定时喊话 删除 任务ID
        """
        if len(parts) < 3:
            await self.send_message("❌ 格式错误\n正确格式：定时喊话 删除 任务ID\n使用'定时喊话 列表'查看任务ID")
            return
            
        try:
            task_id = int(parts[2])
        except ValueError:
            await self.send_message("❌ 任务ID必须是数字\n使用'定时喊话 列表'查看任务ID")
            return
            
        # 先检查任务是否存在且属于当前群组
        group_id = str(self.message.get("group_id"))
        tasks, _ = self.db.list_announcements(group_id=group_id, user_id=user_id)
        task_exists = any(task['id'] == task_id for task in tasks)
        
        if not task_exists:
            await self.send_message("❌ 任务不存在或不属于当前群组")
            return
            
        success, result_msg = self.db.delete_announcement(task_id, user_id)
        
        if success:
            await self.send_message(f"✅ {result_msg}")
        else:
            await self.send_message(f"❌ {result_msg}")
            
    async def list_announcements(self, user_id: str, group_id: str):
        """
        列出定时喊话任务
        格式：定时喊话 列表
        """
        tasks, result_msg = self.db.list_announcements(group_id=group_id, user_id=user_id)
        
        if not tasks:
            await self.send_message("📭 当前没有定时喊话任务")
            return
            
        response = "📋 定时喊话任务列表：\n\n"
        
        for task in tasks:
            status = "✅ 启用" if task['enabled'] else "❌ 禁用"
            days_str = self._format_days_of_week(task['days_of_week'])
            created_time = datetime.fromisoformat(task['created_time']).strftime("%Y-%m-%d %H:%M")
            
            # 检查是否包含@全体成员标记
            message = task['message']
            at_all = message.startswith('[atall]')
            display_message = message[7:] if at_all else message
            at_all_str = "✅ @全体成员" if at_all else "❌ 不@全体成员"
            
            response += (
                f"🆔 ID：{task['id']}\n"
                f"⏰ 时间：{task['hour']:02d}:{task['minute']:02d}\n"
                f"📝 内容：{display_message}\n"
                f"📆 星期：{days_str}\n"
                f"🔔 {at_all_str}\n"
                f"📅 创建：{created_time}\n"
                f"📊 状态：{status}\n"
                f"────────────────────\n"
            )
            
        await self.send_message(response)
        
    async def clear_all_announcements(self, user_id: str, group_id: str):
        """
        清除当前群组的所有定时喊话任务
        格式：定时喊话 清除
        """
        # 获取当前群组的所有任务
        tasks, _ = self.db.list_announcements(group_id=group_id, user_id=user_id)
        
        if not tasks:
            await self.send_message("📭 当前群组没有定时喊话任务")
            return
        
        # 确认清除
        await self.send_message(
            f"⚠️ 确认清除当前群组的所有定时喊话任务吗？\n"
            f"📊 将删除 {len(tasks)} 个任务\n"
            f"📝 请输入：定时喊话 确认清除"
        )
        
    async def confirm_clear_all(self, user_id: str, group_id: str):
        """
        确认清除当前群组的所有定时喊话任务
        格式：定时喊话 确认清除
        """
        # 获取当前群组的所有任务
        tasks, _ = self.db.list_announcements(group_id=group_id, user_id=user_id)
        
        if not tasks:
            await self.send_message("📭 当前群组没有定时喊话任务")
            return
        
        # 删除所有任务
        deleted_count = 0
        for task in tasks:
            success, _ = self.db.delete_announcement(task['id'], user_id)
            if success:
                deleted_count += 1
        
        if deleted_count > 0:
            await self.send_message(f"✅ 已清除当前群组的所有定时喊话任务\n📊 共删除 {deleted_count} 个任务")
        else:
            await self.send_message("❌ 清除任务失败，请稍后重试")
        
    async def toggle_announcement(self, parts: list, user_id: str, enable: bool):
        """
        启用/禁用定时喊话任务
        格式：定时喊话 启用/禁用 任务ID
        """
        if len(parts) < 3:
            action = "启用" if enable else "禁用"
            await self.send_message(f"❌ 格式错误\n正确格式：定时喊话 {action} 任务ID\n使用'定时喊话 列表'查看任务ID")
            return
            
        try:
            task_id = int(parts[2])
        except ValueError:
            await self.send_message("❌ 任务ID必须是数字\n使用'定时喊话 列表'查看任务ID")
            return
            
        # 先检查任务是否存在且属于当前群组
        group_id = str(self.message.get("group_id"))
        tasks, _ = self.db.list_announcements(group_id=group_id, user_id=user_id)
        task_exists = any(task['id'] == task_id for task in tasks)
        
        if not task_exists:
            await self.send_message("❌ 任务不存在或不属于当前群组")
            return
            
        success, result_msg = self.db.toggle_announcement(task_id, user_id)
        
        if success:
            await self.send_message(f"✅ {result_msg}")
        else:
            await self.send_message(f"❌ {result_msg}")
            
    async def show_help(self):
        """
        显示帮助信息
        """
        help_text = """📋 定时喊话功能使用说明：

🔧 基本命令格式：
定时喊话 [命令] [参数]

📝 可用命令：

1. 添加任务：
   定时喊话 添加 HH:MM 消息内容 [星期] [atall]
   例：定时喊话 添加 08:30 早上好
   例：定时喊话 添加 12:00 午饭时间 1,2,3,4,5 atall

2. 删除任务：
   定时喊话 删除 任务ID
   例：定时喊话 删除 1

3. 清除任务：
   定时喊话 清除
   例：定时喊话 清除（需要确认：定时喊话 确认清除）

4. 查看任务：
   定时喊话 列表

5. 启用/禁用任务：
   定时喊话 启用 任务ID
   定时喊话 禁用 任务ID

6. 显示帮助：
   喊话帮助 或 喊话菜单

📌 参数说明：
- HH:MM：24小时制时间，如08:30、14:00
- 消息内容：喊话的文本内容
- 星期：可选，1-7的数字，用逗号分隔
  1=周一，2=周二，3=周三，4=周四，5=周五，6=周六，7=周日
  默认：每天（1,2,3,4,5,6,7）
- atall：可选，在消息后加上"atall"表示@全体成员

⚠️ 注意事项：
- 需要群组管理员权限（3级权限）
- 每个用户只能管理自己创建的任务
- 同一时间、同一群组、相同内容的任务不能重复添加
- @全体成员功能需要机器人有相应权限
- 清除功能会删除当前群组的所有任务，需要二次确认"""
        
        await self.send_message(help_text)
        
    def _format_days_of_week(self, days: list) -> str:
        """
        格式化星期显示
        """
        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        
        if len(days) == 7:
            return "每天"
        elif days == [1, 2, 3, 4, 5]:
            return "工作日"
        elif days == [6, 7]:
            return "周末"
        else:
            return "、".join([day_names[day-1] for day in sorted(days)])
            
    async def send_message(self, message: str):
        """
        发送消息到群组
        """
        if self.message.get("message_type") == "group":
            await QQAPI_list(self.websocket).send_group_message(
                self.message["group_id"], 
                message
            )
        else:
            await QQAPI_list(self.websocket).send_message(
                self.message["user_id"], 
                message
            )


class AnnouncementChecker:
    """
    定时喊话检查器，用于定时检查并执行喊话任务
    """
    def __init__(self, websocket):
        self.logger = Logger("AnnouncementChecker")
        self.websocket = websocket
        self.db = StoreAnnouncement()
        self.api = QQAPI_list(websocket)
        
    async def check_and_execute(self):
        """
        检查并执行到期的喊话任务
        """
        try:
            due_tasks = self.db.get_due_announcements()
            
            if not due_tasks:
                return
                
            self.logger.info(f"发现 {len(due_tasks)} 个待执行喊话任务")
            
            for task in due_tasks:
                try:
                    message = task['message']
                    group_id = task['group_id']
                    
                    # 检查是否需要@全体成员
                    if message.startswith('[atall]'):
                        # 移除标记
                        actual_message = message[7:]  # 移除[atall]标记
                        
                        # 发送@全体成员的消息
                        await self.api.send_at_group_message(
                            group_id,
                            "all",  # @全体成员
                            f"⏰ 定时喊话提醒：\n{actual_message}"
                        )
                        self.logger.info(f"已执行喊话任务 {task['id']}，群组：{group_id}，@全体成员")
                    else:
                        # 发送普通消息
                        await self.api.send_group_message(
                            group_id,
                            f"⏰ 定时喊话提醒：\n{message}"
                        )
                        self.logger.info(f"已执行喊话任务 {task['id']}，群组：{group_id}")
                    
                    # 更新最后执行时间
                    self.db.update_last_executed(task['id'])
                    
                except Exception as e:
                    self.logger.error(f"执行喊话任务 {task['id']} 失败：{e}")
                    
        except Exception as e:
            self.logger.error(f"检查喊话任务失败：{e}")
