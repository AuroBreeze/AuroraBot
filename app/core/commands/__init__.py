"""
统一命令注册中心

其他 app 接入方式：
    from app.core.commands import registry, Command

    async def my_handler(websocket, message) -> tuple[bool, str | None]:
        return True, "结果"

    registry.register(Command(
        name="/mycmd",
        aliases=["mycmd", "我的命令"],
        handler=my_handler,
        description="我的命令说明",
        usage="<参数>",
        required_level=3,
        app_name="我的App",
    ))

分发：registry.dispatch(websocket, message) 在消息入口统一调用。
帮助：/help 输出按权限过滤的分组菜单；/help <命令> 查看详情。
"""
from .model import Command, CommandHandler
from .registry import CommandRegistry, registry, LEVEL_NAMES

__all__ = ["Command", "CommandHandler", "CommandRegistry", "registry", "LEVEL_NAMES"]
