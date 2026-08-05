"""群管命令注册（app/group_manager/commands.py）"""

from app.core.commands import registry, Command
from app.core.hot_reload import hot_reloader
from app.permission.constants import LEVEL_SYSTEM, LEVEL_ADMIN
from . import events  # noqa: F401  （确保事件订阅注册；events 为接线层，不纳入热更新）
from .service import group_manager_service
from . import config as gm_config

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
    return True, await group_manager_service.query_member(group_id, target)


async def _tier_handler(websocket, message) -> tuple[bool, str]:
    """/tier [目标用户]：查看成员游戏段位"""
    group_id = str(message.get("group_id", ""))
    target = _parse_target(str(message.get("raw_message", "")), str(message.get("user_id")))
    return True, await group_manager_service.query_member(group_id, target)


async def _backfill_handler(websocket, message) -> tuple[bool, str]:
    """/backfill [群号]：批量补记录（指定群或全部已授权群）"""
    parts = str(message.get("raw_message", "")).split()
    if len(parts) > 1 and parts[1].isdigit():
        added, total = await group_manager_service.backfill_group(parts[1])
        return True, f"群 {parts[1]} 补记录完成：新增 {added}/{total}"
    return True, await group_manager_service.backfill_all()


async def _members_handler(websocket, message) -> tuple[bool, str]:
    """/members [页码]：批量显示本群成员信息（加入/活跃/段位/段位时间）"""
    group_id = str(message.get("group_id", ""))
    parts = str(message.get("raw_message", "")).split()
    page = 1
    if len(parts) > 1 and parts[1].isdigit():
        page = int(parts[1])
    return True, group_manager_service.list_members(group_id, page)


async def _gm_config_handler(websocket, message) -> tuple[bool, str]:
    """/gm_config [set <键> <值>]：查看/修改群管配置"""
    parts = str(message.get("raw_message", "")).strip().split()
    if len(parts) == 1:
        return True, gm_config.dump()
    if len(parts) >= 3 and parts[1] == "set":
        ok, msg = gm_config.set(parts[2], " ".join(parts[3:]))
        return True, msg
    return True, "用法：/gm_config 查看全部配置；/gm_config set <键> <值> 修改"


def _register():
    registry.register(Command(
        name="/members",
        aliases=["members"],
        handler=_members_handler,
        description="批量显示本群成员信息（加入/活跃/段位/段位时间）",
        usage="[页码，默认 1]",
        detail="分页（每页 20 人）显示群成员档案：加入时间、最后活跃、\n"
               "游戏段位、段位登记时间。段位未登记/时间缺失显示 -。",
        example="/members\n/members 2",
        required_level=LEVEL_ADMIN, app_name=APP,
    ))
    registry.register(Command(
        name="/backfill",
        aliases=["backfill"],
        handler=_backfill_handler,
        description="存量成员批量补记录",
        usage="[群号，缺省=全部已授权群]",
        detail="拉取真实群成员列表，补齐 MemberStore 缺失的成员记录\n"
               "（已存在记录不被覆盖；仅处理已授权群）。",
        example="/backfill\n/backfill 123456789",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
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
    registry.register(Command(
        name="/gm_config",
        aliases=["gm_config", "群管配置"],
        handler=_gm_config_handler,
        description="查看/修改群管配置（无需重启，立即生效）",
        usage="查看：/gm_config；修改：/gm_config set <键> <值>",
        detail="查看全部可配置项及当前值；修改后立即生效并写回配置文件。\n"
               "文本含换行请用 \\n；布尔用 true/false。",
        example="/gm_config\n/gm_config set inactive_kick_enabled true\n"
                "/gm_config set welcome_msg 第一行\\n第二行",
        required_level=LEVEL_SYSTEM, app_name=APP,
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
