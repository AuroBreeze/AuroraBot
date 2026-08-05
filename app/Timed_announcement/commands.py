"""定时喊话命令注册（模块导入时执行，供消息分发器统一使用）"""

from app.core.commands import registry, Command
from app.permission.constants import LEVEL_ADMIN


def _register():
    from .announcement_main import TimedAnnouncement

    async def _ta_handler(websocket, message):
        # 定时喊话内部自行发送回复，注册中心只负责匹配与鉴权
        await TimedAnnouncement(websocket, message).handle_event()
        return True, None

    registry.register(Command(
        name="/announce",
        aliases=["announce", "timed_announcement"],
        handler=_ta_handler,
        description="设置与管理定时喊话任务（需群管理员权限）",
        usage="添加 <HH:MM> <内容> [星期1-7] [atall]\n列表\n删除 <任务ID>\n启用 <任务ID>\n禁用 <任务ID>",
        required_level=LEVEL_ADMIN,
        app_name="定时喊话",
        sub_commands={
            "添加": "添加定时喊话任务（星期用逗号分隔；末尾 atall 表示@全体）",
            "列表": "查看自己的喊话任务列表",
            "删除": "删除自己的喊话任务",
            "启用": "启用任务",
            "禁用": "禁用任务",
        },
    ))


_register()
