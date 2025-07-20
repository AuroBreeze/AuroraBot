from config import env
import asyncio
from typing import Dict

ADMIN_ID = env.QQ_ADMIN if env.QQ_ADMIN else "" # 管理员QQ号

add_text = ""
time_interval: int = 1 # 定时发送间隔,单位 秒
active_tasks: Dict[str, asyncio.Task] = {}  # 各群组的异步发送任务 {group_id: task}

def get_active_tasks() -> Dict[str, asyncio.Task]:
    global active_tasks
    return active_tasks
