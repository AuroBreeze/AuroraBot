"""命令模型定义"""

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

# handler 统一签名: async (websocket, message) -> (judge, reply_msg)
#   reply_msg 为 None 时由分发器不发送（命令内部已自行处理）
CommandHandler = Callable[[object, dict], Awaitable[tuple[bool, Optional[str]]]]


@dataclass
class Command:
    """一条命令的注册信息"""
    name: str                    # 主命令名（匹配首词），如 "/list_users"
    handler: CommandHandler      # 处理函数
    description: str = ""        # 一句话说明（帮助菜单展示）
    usage: str = ""              # 参数格式示例（帮助菜单/详情展示）
    detail: str = ""             # 详细说明（/help <命令> 展示，多行）
    example: str = ""            # 使用示例（/help <命令> 展示，多行）
    required_level: int = 3      # 所需权限级别（1=管理员 2=群主 3=群管理员 4=所有人）
    app_name: str = ""           # 所属 app（帮助分组名）
    aliases: list = field(default_factory=list)   # 别名（如 "list_user"）
    sub_commands: dict = field(default_factory=dict)  # 子命令名 -> 说明（帮助展示）

    def __post_init__(self):
        # 主命令名与别名必须互不相同且不重复
        keys = [self.name] + list(self.aliases)
        if len(set(keys)) != len(keys):
            raise ValueError(f"命令 {self.name} 的别名存在重复")
