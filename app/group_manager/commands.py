"""群管命令注册（app/group_manager/commands.py）"""

from app.core.commands import registry, Command
from app.core.hot_reload import hot_reloader
from app.permission.constants import LEVEL_ADMIN
from . import events  # noqa: F401  （确保事件订阅注册；events 为接线层，不纳入热更新）
from .service import group_manager_service

APP = "群管"


def _parse_target(raw: str, user_id: str) -> str:
    """解析目标用户：优先 @；其次显式 QQ；缺省为命令发起者"""
    at = group_manager_service.parse_at(raw)
    if at:
        return at
    parts = raw.split()
    if len(parts) > 1 and parts[1].isdigit():
        return parts[1]
    return user_id


async def _active_handler(websocket, message) -> tuple[bool, str]:
    """/active [目标用户]：查看成员活跃信息"""
    group_id = str(message.get("group_id", ""))
    target = _parse_target(str(message.get("raw_message", "")), str(message.get("user_id")))
    return True, group_manager_service.query_member(group_id, target)


async def _tier_handler(websocket, message) -> tuple[bool, str]:
    """/tier [目标用户]：查看成员游戏段位"""
    group_id = str(message.get("group_id", ""))
    target = _parse_target(str(message.get("raw_message", "")), str(message.get("user_id")))
    return True, group_manager_service.query_member(group_id, target)


def _register():
    registry.register(Command(
        name="/active",
        aliases=["active"],
        handler=_active_handler,
        description="查看成员活跃信息（入群时间/最后发言/段位）",
        usage="[目标用户，默认自己]",
        detail="查看群成员档案：入群时间、最后发言时间、游戏段位。\n"
               "目标用户可为 @ 或 QQ 号；缺省为命令发起者。",
        example="/active\n/active 88888888",
        required_level=LEVEL_ADMIN, app_name=APP,
    ))
    registry.register(Command(
        name="/tier",
        aliases=["tier"],
        handler=_tier_handler,
        description="查看成员游戏段位",
        usage="[目标用户，默认自己]",
        detail="查看群成员登记的游戏段位（入群时询问登记）。\n"
               "目标用户可为 @ 或 QQ 号；缺省为命令发起者。",
        example="/tier\n/tier 88888888",
        required_level=LEVEL_ADMIN, app_name=APP,
    ))

    # 热更新清单：service + commands（events 为接线层不重载）
    hot_reloader.register_app(
        APP,
        modules=[
            "app.group_manager.service",
            "app.group_manager.commands",
        ],
    )


_register()
