"""Lssuing 权限系统命令注册（模块导入时执行，供消息分发器统一使用）

注册顺序按权限级别分组（系统管理员 → 群主 → 群管理员），组内按命令名排序；
/help 菜单输出时还会按（权限级别, 命令名）再次排序，与注册顺序无关。
每条命令的 detail（详细说明）与 example（示例）通过 /help <命令> 展示。
"""

from functools import partial

from app.core.commands import registry, Command
from app.permission.constants import LEVEL_SYSTEM, LEVEL_OWNER, LEVEL_ADMIN


def _register():
    from .services.admin.group_service import GroupService as AdminGroupService
    from .services.admin.user_service import UserService as AdminUserService
    from .services.user.group_service import GroupService as UserGroupService
    from .services.user.user_service import UserService as UserUserService

    admin_group = AdminGroupService()
    admin_user = AdminUserService()
    user_group = UserGroupService()
    user_user = UserUserService()

    APP = "权限系统"

    # ---- 系统管理员（1 级）：群组与用户授权管理 ----
    registry.register(Command(
        name="/check_groups",
        aliases=["check_groups", "check_group_list"],
        handler=partial(admin_group.check_group_list_and_kick),
        description="检查并踢出过期授权群",
        usage="",
        detail="遍历所有授权群，将已过期的群移除授权（级联清理该群全部用户权限）；"
               "即将过期（3 天内）的群会提示剩余天数。",
        example="/check_groups",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
    registry.register(Command(
        name="/grant",
        aliases=["grant", "raise_user"],
        handler=partial(admin_user.raise_user_permission),
        description="跨群设置用户权限",
        usage="<目标群号> <目标用户> <级别2或3>",
        detail="系统管理员跨群设置用户权限级别：2=群主/付费用户，3=群管理员。\n"
               "目标用户已有同级或更高权限时会被拒绝，防止覆盖降级。",
        example="/grant 123456789 88888888 3\n"
                "# 给 88888888 在群 123456789 授予群管理员权限",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
    registry.register(Command(
        name="/remove_user",
        aliases=["remove_user"],
        handler=partial(admin_user.remove_user_permission),
        description="跨群移除用户权限",
        usage="<目标群号> <目标用户>",
        detail="系统管理员跨群移除用户的全部权限（用户权限与群授权信息一并清除）。",
        example="/remove_user 123456789 88888888",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
    registry.register(Command(
        name="/sub_group",
        aliases=["sub_group"],
        handler=partial(admin_group.authorize_group_simple),
        description="登记授权群组（简单版：now 起生效，功能 all）",
        usage="<目标群号> <天数> [获权用户，默认自己]",
        detail="简单版群授权：登记授权群组并写入授权时段（立即生效，功能 all）。\n"
               "获权用户即该群 2 级（群主/付费用户），缺省为命令执行者；\n"
               "授权后自动识别该群真实群主并授予 2 级权限（与获权用户不同时）。",
        example="/sub_group 123456789 30\n"
                "# 授权群 123456789 使用 30 天，获权用户=自己\n"
                "/sub_group 123456789 30 88888888\n"
                "# 授权 30 天，获权用户=88888888",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
    registry.register(Command(
        name="/subscribe_group",
        aliases=["subscribe"],
        handler=partial(admin_group.authorize_group),
        description="登记授权群组（完整版：可指定起止时间与功能）",
        usage="<目标群号>\nstarttime now\nendtime <天数>\nuser_id <获权用户>\nfeatures all",
        detail="完整版群授权：可指定起止时间与授权功能（多行参数格式）。\n"
               "starttime 可为 now 或 %Y-%m-%d %H:%M:%S；endtime 为授权天数；\n"
               "授权后自动识别该群真实群主并授予 2 级权限（与获权用户不同时）。",
        example="subscribe_group 123456789\n"
                "starttime now\n"
                "endtime 30\n"
                "user_id 88888888\n"
                "features all",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
    registry.register(Command(
        name="/unsub",
        aliases=["unsub", "unsubscribe", "unsubscribe_group"],
        handler=partial(admin_group.remove_authorization),
        description="取消群组授权（级联删除该群权限）",
        usage="<目标群号>",
        detail="取消群组授权，同时级联删除该群全部用户权限。",
        example="/unsub 123456789",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))

    # ---- 群主（2 级）：本群用户权限管理 ----
    registry.register(Command(
        name="/promote",
        aliases=["promote"],
        handler=partial(user_user.raise_user_permission),
        description="将本群用户提升为群管理员",
        usage="<目标用户>",
        detail="本群内将普通用户提升为群管理员（3 级），仅 2 级（群主）可用。\n"
               "目标用户已有同级或更高权限时会被拒绝。",
        example="/promote 66666666",
        required_level=LEVEL_OWNER, app_name=APP,
    ))
    registry.register(Command(
        name="/revoke",
        aliases=["revoke"],
        handler=partial(user_user.remove_user_permission),
        description="移除本群低一级用户的权限",
        usage="<目标用户>",
        detail="移除本群低一级用户（3 级群管理员）的权限，仅 2 级（群主）可用。",
        example="/revoke 66666666",
        required_level=LEVEL_OWNER, app_name=APP,
    ))

    # ---- 群管理员（3 级）：本群信息查询 ----
    registry.register(Command(
        name="/group_info",
        aliases=["group_info"],
        handler=partial(user_group.check_group_information),
        description="查看本群授权信息",
        usage="",
        detail="查看本群授权信息：获权用户、授权起止时间、授权功能。",
        example="/group_info",
        required_level=LEVEL_ADMIN, app_name=APP,
    ))
    registry.register(Command(
        name="/list_users",
        aliases=["list_users", "list_user"],
        handler=partial(user_group.list_user_permissions),
        description="列出群组授权用户（仅本群或管理员）",
        usage="<目标群号>",
        detail="列出指定群的授权用户及权限级别、上级授权人。\n"
               "仅限本群用户或系统管理员查看（防跨群枚举）。",
        example="/list_users 123456789",
        required_level=LEVEL_ADMIN, app_name=APP,
    ))


_register()
