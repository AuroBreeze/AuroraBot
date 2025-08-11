from config import env
import asyncio
from typing import Dict

ADMIN_ID = env.QQ_ADMIN if env.QQ_ADMIN else "" # 管理员QQ号

add_text = ""
time_interval: int = 1000 # 定时发送间隔

DB_PATH = "./store/db/"# database path 数据库路径


active_tasks: Dict[str, asyncio.Task] = {}  # 各群组的异步发送任务 {group_id: task}
waiting_for_file: Dict[str, bool] = {}  # 等待文件状态 {excutor_id: bool}

stop_flags: Dict[str, bool] = {}  # 停止标志 {group_id: bool}
group_name_tasks: Dict[str, asyncio.Task] = {}  # 群名修改任务 {group_id: task}
current_group_names: Dict[str, str] = {}  # 当前群名 {group_id: name}
group_name_timers: Dict[str, float] = {}  # 群名修改计时 {group_id: 剩余秒数}

waiting_for_file = {} 
waiting_for_avatar = {}  # 新增等待头像状态字典

# 跟随@回复状态：每个群一份，记录目标QQ、要发送的行、当前索引等
follow_talk_state: Dict[str, dict] = {}

def get_active_tasks() -> Dict[str, asyncio.Task]:
    global active_tasks
    return active_tasks
    
def get_stop_flags() -> Dict[str, bool]:
    global stop_flags
    return stop_flags

def get_follow_talk_state() -> Dict[str, dict]:
    global follow_talk_state
    return follow_talk_state
