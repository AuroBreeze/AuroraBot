"""注册内建 /help 命令（模块导入时执行）"""

from app.permission.constants import LEVEL_NONE
from .model import Command
from .registry import registry


async def _help_handler(websocket, message):
    """/help [命令名]：输出按权限过滤的分组菜单，或单个命令详情"""
    raw = str(message.get("raw_message", ""))
    group_id = message.get("group_id")
    user_id = str(message.get("user_id"))
    parts = raw.strip().split(" ", 1)
    target = ""
    if len(parts) > 1 and parts[1].strip():
        target = parts[1].strip().split(" ", 1)[0]
    return True, registry.help_text(group_id, user_id, target)


registry.register(Command(
    name="/help",
    aliases=["help"],
    handler=_help_handler,
    description="查看命令菜单与帮助",
    usage="[命令名]",
    required_level=LEVEL_NONE,  # 所有用户可用
    app_name="系统",
))
