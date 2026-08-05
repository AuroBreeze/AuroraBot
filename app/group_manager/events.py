"""
群管事件订阅（app/group_manager/events.py）

接线层：订阅事件总线，业务逻辑延迟引用 service（热更新 service 后自动生效）。
本模块不纳入热更新清单（订阅接线保持稳定）。

- GROUP_INCREASE：入群引导（欢迎/规则/链接 + 段位询问 + 观察期）
- GROUP_REQUEST：自动同意入群（按配置策略）
- MESSAGE：活跃记录 + 段位回复状态机
"""
from api.Logger_owner import Logger
from app.core.events import event_bus, EventType

_handlers = []  # 已注册的 (EventType, handler)，供幂等退订


async def _on_group_increase(event):
    from .service import group_manager_service
    await group_manager_service.on_member_join(event)


async def _on_group_request(event):
    from .service import group_manager_service
    await group_manager_service.handle_group_request(event)


async def _on_message(event):
    from .service import group_manager_service
    from . import config as gm_config
    if not gm_config.get_bool("enabled", True):
        return  # 群管总开关关闭：不记录活跃、不走段位状态机
    if event.data.get("message_type") != "group":
        return
    group_id = str(event.group_id or "")
    user_id = event.user_id
    if not group_id or not user_id:
        return
    # 群主观察期回复（同意/拒绝移出）优先处理
    await group_manager_service.handle_observe_reply(event)
    # 活跃记录（高频，同步写库）顺带保存发言者昵称
    sender = event.data.get("sender") or {}
    group_manager_service.record_active(group_id, user_id, str(sender.get("nickname") or "") or None)
    # 段位回复状态机
    await group_manager_service.handle_tier_reply(event)


def subscribe_events() -> None:
    """注册事件订阅（幂等：先退订本模块已注册的 handler 再重新订阅）"""
    global _handlers
    for event_type, handler in _handlers:
        event_bus.unsubscribe(event_type, handler)
    _handlers = [
        (EventType.GROUP_INCREASE, _on_group_increase),
        (EventType.GROUP_REQUEST, _on_group_request),
        (EventType.MESSAGE, _on_message),
    ]
    for event_type, handler in _handlers:
        event_bus.subscribe(event_type, handler)
    Logger("group_manager_events").info(f"群管事件订阅已注册: {[t.value for t, _ in _handlers]}")


# 模块加载即订阅
subscribe_events()
