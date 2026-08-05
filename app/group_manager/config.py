"""
群管配置（app/group_manager/config.py）

从 config/group_manager.yml 加载；文件缺失时使用内置默认值。
配置修改后需重启（或调用 reload_config() 热加载）。
"""
import os

from api.Logger_owner import Logger
import yaml

CONFIG_PATH = os.path.join("config", "group_manager.yml")

DEFAULTS = {
    "enabled": True,                # 总开关
    "observe_minutes": 10,          # 观察期（分钟）：入群后未发言踢出
    "auto_approve": True,           # 自动同意入群
    "auto_approve_scope": "authorized",  # authorized=仅已授权群; all=全部
    "welcome_msg": "欢迎 {user} 加入本群！\n请阅读群规：\n{rules}\n{link}\n\n{question}",
    "rules_msg": "入群 {minutes} 分钟内未发言将被移出群聊，请尽快发言报到。",
    "link": "",
    "tier_question": "请回复您的游戏段位（如：王者、钻石、铂金…），回复任意文字即可登记：",
    "tier_confirm": "✅ 已登记您的段位：{tier}",
    "tier_denied": "⚠️ 段位登记失败，请稍后重试。",
}

_config = dict(DEFAULTS)
_loaded = False


def _ensure_default_file() -> None:
    """首次运行时生成默认配置文件（便于用户修改）"""
    if os.path.exists(CONFIG_PATH):
        return
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(DEFAULTS, f, allow_unicode=True, sort_keys=False)
    except OSError as e:
        Logger("group_manager_config").warning(f"无法生成默认配置 {CONFIG_PATH}: {e}")


def load_config() -> dict:
    """加载配置（yml 覆盖默认值）；重复调用重新读取"""
    global _config, _loaded
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            cfg.update({k: v for k, v in loaded.items() if v is not None})
        except Exception as e:
            Logger("group_manager_config").error(f"配置加载失败，使用默认值: {e}")
    _config = cfg
    _loaded = True
    return _config


def reload_config() -> dict:
    return load_config()


def get() -> dict:
    if not _loaded:
        load_config()
    return _config


def get_str(key: str, default: str = "") -> str:
    return str(get().get(key, default) or default)


def get_int(key: str, default: int = 0) -> int:
    try:
        return int(get().get(key, default))
    except (TypeError, ValueError):
        return default


def get_bool(key: str, default: bool = False) -> bool:
    return bool(get().get(key, default))


# 模块加载时：生成默认配置文件并加载
_ensure_default_file()
load_config()
