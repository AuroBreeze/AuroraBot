"""
群管配置（app/group_manager/config.py）

从 config/group_manager.yml 加载；文件缺失时使用内置默认值。
配置修改后需重启（或调用 reload_config() 热加载）。
"""
import os

from api.Logger_owner import Logger
import yaml

CONFIG_PATH = os.path.join("config", "group_manager.yml")

# 可配置项白名单：类型 + 描述（/gm_config 命令查看与修改）
CONFIG_KEYS = {
    "enabled":                {"type": bool, "desc": "群管总开关"},
    "observe_minutes":        {"type": int,  "desc": "入群观察期（分钟），期内未发言将被移出"},
    "auto_approve":           {"type": bool, "desc": "自动同意入群申请"},
    "auto_approve_scope":     {"type": str,  "desc": "自动同意范围：authorized=仅授权群 / all=全部群"},
    "auto_backfill":          {"type": bool, "desc": "自动补记录：未处理过的群自动补一次成员记录"},
    "auto_backfill_interval": {"type": int,  "desc": "自动补记录检查间隔（秒）"},
    "active_sync_enabled":    {"type": bool, "desc": "API 活跃同步开关（get_group_member_info 遍历授权群成员）"},
    "active_sync_interval":   {"type": int,  "desc": "API 活跃同步间隔（秒）"},
    "inactive_kick_enabled":  {"type": bool, "desc": "不活跃自动踢人开关"},
    "inactive_kick_days":     {"type": int,  "desc": "不活跃阈值（天）"},
    "inactive_remind_days":   {"type": int,  "desc": "踢前提醒（剩余天数）"},
    "inactive_kick_interval": {"type": int,  "desc": "不活跃扫描间隔（秒）"},
    "welcome_msg":            {"type": str,  "desc": "入群欢迎语（{user}{rules}{link}{question}，\\n 换行）"},
    "rules_msg":              {"type": str,  "desc": "群规提示（{minutes}，\\n 换行）"},
    "link":                   {"type": str,  "desc": "引导链接（留空则不发送）"},
    "tier_question":          {"type": str,  "desc": "段位询问文案（\\n 换行）"},
    "tier_confirm":           {"type": str,  "desc": "段位登记成功文案（{tier}）"},
    "tier_denied":            {"type": str,  "desc": "段位登记失败文案"},
    "inactive_remind_msg":    {"type": str,  "desc": "不活跃提醒文案（{days}{left}）"},
}

# 配置文件路径（测试可替换为临时路径）
_config_path = CONFIG_PATH

DEFAULTS = {
    "enabled": True,                # 总开关
    "observe_minutes": 10,          # 观察期（分钟）：入群后未发言踢出
    "auto_approve": True,           # 自动同意入群
    "auto_approve_scope": "authorized",  # authorized=仅已授权群; all=全部
    "auto_backfill": True,          # 自动补记录：未处理过的群自动补一次
    "auto_backfill_interval": 300,  # 自动补记录检查间隔（秒）
    "active_sync_enabled": True,    # API 活跃同步开关（get_group_member_info 遍历授权群成员）
    "active_sync_interval": 3600,   # API 活跃同步间隔（秒）
    "inactive_kick_enabled": False, # 不活跃自动踢人开关（默认关闭，需手动开启）
    "inactive_kick_days": 7,        # 不活跃阈值（天）
    "inactive_remind_days": 1,      # 踢前提醒（剩余天数）
    "inactive_kick_interval": 3600, # 不活跃扫描间隔（秒）
    "inactive_remind_msg": "⚠️ 您已超过 {days} 天未发言，{left} 天后将被移出群聊，请尽快发言报到！",
    "welcome_msg": "欢迎 {user} 加入本群！\n请阅读群规：\n{rules}\n{link}\n\n{question}",
    "rules_msg": "入群 {minutes} 分钟内发言即可避免被移出群聊，请尽快发言报到。",
    "link": "",
    "tier_question": "（选填）回复此条消息可登记您的游戏段位及游玩时间，方便群管理，如：王者",
    "tier_confirm": "✅ 已登记您的段位：{tier}",
    "tier_denied": "⚠️ 段位登记失败，请稍后重试。",
}

_config = dict(DEFAULTS)
_loaded = False


def _ensure_default_file() -> None:
    """首次运行时生成默认配置文件（便于用户修改）"""
    if os.path.exists(_config_path):
        return
    try:
        os.makedirs(os.path.dirname(_config_path), exist_ok=True)
        with open(_config_path, "w", encoding="utf-8") as f:
            yaml.dump(DEFAULTS, f, allow_unicode=True, sort_keys=False)
    except OSError as e:
        Logger("group_manager_config").warning(f"无法生成默认配置 {_config_path}: {e}")


def load_config() -> dict:
    """加载配置（yml 覆盖默认值）；重复调用重新读取"""
    global _config, _loaded
    cfg = dict(DEFAULTS)
    if os.path.exists(_config_path):
        try:
            with open(_config_path, "r", encoding="utf-8") as f:
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


def set(key: str, value) -> tuple:
    """运行时修改配置并写回 yml；返回 (ok, msg)"""
    if key not in CONFIG_KEYS:
        return False, f"未知配置项：{key}（可用 /gm_config 查看全部可配置项）"
    spec = CONFIG_KEYS[key]
    try:
        converted = _convert(spec["type"], value)
    except ValueError as e:
        return False, str(e)
    cfg = get()
    cfg[key] = converted
    if not _persist(cfg):
        return False, f"配置写回失败，修改未生效（内存中已更新 {key}={converted}）"
    Logger("group_manager_config").info(f"配置已更新 {key} = {converted}")
    return True, f"✅ 已设置 {key} = {converted}"


def dump() -> str:
    """格式化输出当前配置（含描述）"""
    cfg = get()
    lines = ["📋 群管配置"]
    for key, spec in CONFIG_KEYS.items():
        val = cfg.get(key, spec["type"]())
        shown = str(val).replace("\n", "\\n")
        lines.append(f"  {key} = {shown}\n      （{spec['desc']}）")
    lines.append("💡 修改：/gm_config set <键> <值>（文本含换行请用 \\n）")
    return "\n".join(lines)


def _convert(typ, value):
    if typ is bool:
        v = str(value).strip().lower()
        if v in ("true", "1", "yes", "on", "开", "开启"):
            return True
        if v in ("false", "0", "no", "off", "关", "关闭"):
            return False
        raise ValueError(f"布尔值需为 true/false，收到：{value}")
    if typ is int:
        try:
            return int(str(value).strip())
        except ValueError:
            raise ValueError(f"整数需为数字，收到：{value}")
    return str(value).replace("\\n", "\n")  # 文本：字面 \n 转真实换行


def _persist(cfg: dict) -> bool:
    """写回配置文件"""
    try:
        with open(_config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)
        return True
    except OSError as e:
        Logger("group_manager_config").error(f"配置写回失败: {e}")
        return False


# 模块加载时：生成默认配置文件并加载
_ensure_default_file()
load_config()
