"""
运行时上下文（app/core/runtime.py）

ws 连接建立后注入统一 API 客户端，断开时清空。
事件订阅者/后台任务不持有 websocket，通过 get_api() 获取当前可用客户端。
self_id（bot 自身 QQ）从消息中提取，供业务层避免误伤自己。

    from app.core.runtime import get_api, get_self_id

    api = get_api()
    if api is not None:
        await api.send_group_message(group_id, text)
"""
from typing import Optional

_api = None
_self_id: str = ""


def set_api(api) -> None:
    """ws 连接建立后注入；断开时传 None 清空"""
    global _api
    _api = api


def get_api():
    """获取当前 API 客户端；未连接返回 None"""
    return _api


def is_connected() -> bool:
    return _api is not None


def set_self_id(self_id: str) -> None:
    """记录 bot 自身 QQ（从收到的消息提取；幂等）"""
    global _self_id
    if self_id:
        _self_id = str(self_id)


def get_self_id() -> str:
    """bot 自身 QQ；未知返回 ''"""
    return _self_id
