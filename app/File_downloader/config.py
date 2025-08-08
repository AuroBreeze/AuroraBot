# -*- coding: utf-8 -*-
"""
File_downloader 配置与运行时状态
- group_download_dirs: { group_id: directory }  # 每个群单独设置保存目录
- waiting_for_file: { user_id: bool }          #（兼容保留，当前自动收录无需）
默认下载根目录为 ./store/downloads/
"""
import os
from config.env import QQ_ADMIN

DEFAULT_ROOT = os.path.normpath('./store/downloads')
DEFAULT_ROOT_SET: bool = False  # 是否由管理员主动设置过默认根目录

# 运行时状态（内存）
group_download_dirs: dict[str, str] = {}
waiting_for_file: dict[str, bool] = {}

# 管理员与全局下载开关（仅管理员可控）
ADMIN_ID: str = str(QQ_ADMIN or '').strip()
DOWNLOAD_ENABLED: bool = True  # True 时，任何人发文件都会自动下载

def is_admin(user_id: str) -> bool:
    return ADMIN_ID != '' and str(user_id) == ADMIN_ID

# 确保默认根目录存在
os.makedirs(DEFAULT_ROOT, exist_ok=True)
