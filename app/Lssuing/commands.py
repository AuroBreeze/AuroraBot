"""Lssuing 权限系统命令注册（模块导入时执行，供消息分发器统一使用）"""

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

    registry.register(Command(
        name="/subscribe_group",
        aliases=["subscribe_group"],
        handler=partial(admin_group.authorize_group),
        description="登记授权群组",
        usage="<目标群号>\nstarttime now\nendtime <天数>\nuser_id <获权用户>\nfeatures all",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
    registry.register(Command(
        name="/unsubscribe_group",
        aliases=["unsubscribe_group"],
        handler=partial(admin_group.remove_authorization),
        description="取消群组授权（级联删除该群权限）",
        usage="<目标群号>",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
    registry.register(Command(
        name="/check_group_list",
        aliases=["check_group_list"],
        handler=partial(admin_group.check_group_list_and_kick),
        description="检查并踢出过期授权群",
        usage="",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
    registry.register(Command(
        name="/raise_user",
        aliases=["raise_user"],
        handler=partial(admin_user.raise_user_permission),
        description="跨群提升用户权限（系统管理员）",
        usage="<目标群号> <目标用户> <级别2或3>",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
    registry.register(Command(
        name="/remove_user",
        aliases=["remove_user"],
        handler=partial(admin_user.remove_user_permission),
        description="跨群移除用户权限（系统管理员）",
        usage="<目标群号> <目标用户>",
        required_level=LEVEL_SYSTEM, app_name=APP,
    ))
    registry.register(Command(
        name="/list_user",
        aliases=["list_user"],
        handler=partial(user_group.list_user_permissions),
        description="列出群组授权用户（仅本群或管理员）",
        usage="<目标群号>",
        required_level=LEVEL_ADMIN, app_name=APP,
    ))
    registry.register(Command(
        name="/check_group",
        aliases=["check_group"],
        handler=partial(user_group.check_group_information),
        description="查看本群授权信息",
        usage="",
        required_level=LEVEL_ADMIN, app_name=APP,
    ))
    registry.register(Command(
        name="/remove",
        aliases=["remove"],
        handler=partial(user_user.remove_user_permission),
        description="移除本群低一级用户的权限",
        usage="<目标用户>",
        required_level=LEVEL_OWNER, app_name=APP,
    ))
    registry.register(Command(
        name="/raise",
        aliases=["raise"],
        handler=partial(user_user.raise_user_permission),
        description="将本群用户提升为群管理员",
        usage="<目标用户>",
        required_level=LEVEL_OWNER, app_name=APP,
    ))


_register()
