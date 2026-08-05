"""
运行时上下文（app/core/runtime.py）

ws 连接建立后注入统一 API 客户端，断开时清空。
事件订阅者/后台任务不持有 websocket，通过 get_api() 获取当前可用客户端。

    from app.core.runtime import get_api

    api = get_api()
    if api is not None:
        await api.send_group_message(group_id, text)
"""
from typing import Optional

_api = None


def set_api(api) -> None:
    """ws 连接建立后注入；断开时传 None 清空"""
    global _api
    _api = api


def get_api():
    """获取当前 API 客户端；未连接返回 None"""
    return _api


def is_connected() -> bool:
    return _api is not None
