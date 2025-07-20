from config import env
import asyncio
from typing import Dict

ADMIN_ID = env.QQ_ADMIN if env.QQ_ADMIN else "" # 管理员QQ号

add_text = ""
time_interval: int = 1 # 定时发送间隔
active_tasks: Dict[str, asyncio.Task] = {}  # 各群组的异步发送任务 {group_id: task}
waiting_for_file: Dict[str, bool] = {}  # 等待文件状态 {excutor_id: bool}

stop_flags: Dict[str, bool] = {}  # 停止标志 {group_id: bool}

def get_active_tasks() -> Dict[str, asyncio.Task]:
    global active_tasks
    return active_tasks
    
def get_stop_flags() -> Dict[str, bool]:
    global stop_flags
    return stop_flags
