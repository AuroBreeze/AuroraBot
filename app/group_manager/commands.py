"""群管命令注册（app/group_manager/commands.py）"""

from app.core.commands import registry, Command
from app.core.hot_reload import hot_reloader
from app.core.permission.constants import LEVEL_SYSTEM, LEVEL_ADMIN
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


async def _inactive_handler(websocket, message) -> tuple[bool, str]:
    """/inactive [天数] [页码]：列出本群不活跃成员（@ + 未活跃天数，降序；默认全部列出，显式页码才分页）"""
    from app.core.runtime import get_api
    group_id = str(message.get("group_id", ""))
    parts = str(message.get("raw_message", "")).split()
    days = gm_config.get_int("inactive_kick_days", 7)
    page = 0  # 0 = 全部列出
    if len(parts) > 1 and parts[1].isdigit():
        days = int(parts[1])
    if len(parts) > 2 and parts[2].isdigit():
        page = int(parts[2])
    segs = group_manager_service.list_inactive_members(group_id, days, page)
    api = get_api()
    if api is None:
        return True, "连接不可用，请稍后重试"
    await api.send_group_message_array(group_id, segs)
    return True, ""  # 已通过消息数组发送（@ 正常生效）


async def _kick_handler(websocket, message) -> tuple[bool, str]:
    """/kick 目标...：批量踢人（@ / QQ号 / 上次 /inactive 列表序号）"""
    group_id = str(message.get("group_id", ""))
    operator = str(message.get("user_id", ""))
    return True, await group_manager_service.kick_members(group_id, operator, str(message.get("raw_message", "")))


async def _sync_active_handler(websocket, message) -> tuple[bool, str]:
    """/sync_active [群号]：手动强制刷新活跃；指定群号只刷新该群，否则全部授权群"""
    parts = str(message.get("raw_message", "")).split()
    if len(parts) > 1 and parts[1].isdigit():
        updated, total = await group_manager_service.sync_group_members_active(parts[1])
        return True, f"群 {parts[1]} 刷新完成：更新 {updated}/{total}"
    return True, await group_manager_service.sync_all_groups_active(force=True)


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
    registry.register(Command(
        name="/inactive",
        aliases=["inactive", "不活跃"],
        handler=_inactive_handler,
        description="列出本群不活跃成员（@+未活跃天数，降序）",
        usage="[天数，默认读配置 inactive_kick_days] [页码，默认全部列出]",
        detail="列出本群未活跃成员：每行序号 + @ + 未活跃天数，按天数降序。\n"
               "默认全部列出（不指定页码）；指定页码才分页（每页 10 人）。\n"
               "列表序号可直接用于 /kick 批量移出。",
        example="/inactive\n/inactive 3\n/inactive 7 2",
        required_level=LEVEL_ADMIN, app_name=APP,
    ))
    registry.register(Command(
        name="/kick",
        aliases=["kick", "踢人"],
        handler=_kick_handler,
        description="批量移出不活跃/指定成员（@ / QQ号 / 列表序号）",
        usage="目标...（@用户 / QQ号 / 上次 /inactive 列表序号，可混合）",
        detail="批量移出成员：\n"
               "- @目标：@用户\n"
               "- QQ号：直接输入\n"
               "- 列表序号：先用 /inactive 查看，数字即该列表序号\n"
               "自动跳过：机器人自己/群主管理员/有权限用户/非群成员。",
        example="/kick 1 3\n/kick @user1 @user2\n/kick 1 @user3 123456789",
        required_level=LEVEL_ADMIN, app_name=APP,
    ))
    registry.register(Command(
        name="/sync_active",
        aliases=["sync_active", "同步活跃"],
        handler=_sync_active_handler,
        description="手动强制刷新授权群成员活跃（last_sent_time/nickname）",
        usage="[群号，缺省全部授权群]",
        detail="立即刷新成员最后活跃时间与昵称（无视 active_sync_enabled 开关）。\n"
               "指定群号只刷新该群；无参数刷新全部授权群。",
        example="/sync_active\n/sync_active 736038975",
        required_level=LEVEL_ADMIN, app_name=APP,
    ))

    # 热更新清单：config（依赖最前）→ service → commands（events 为接线层不重载）
    hot_reloader.register_app(
        APP,
        modules=[
            "app.group_manager.config",
            "app.group_manager.service",
            "app.group_manager.commands",
        ],
    )


_register()
