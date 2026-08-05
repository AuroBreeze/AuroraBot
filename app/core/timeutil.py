"""统一时间工具（app/core/timeutil.py）

集中时间格式常量与北京时间转换，避免各处重复定义格式串、时区处理不一致。
"""
from datetime import datetime

import pytz

from config.env import TIMEZONE

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

_bj_tz = pytz.timezone(TIMEZONE)


def bj_now() -> datetime:
    """当前北京时间（带时区）"""
    return datetime.now(_bj_tz)


def now_str() -> str:
    """当前北京时间 → 存储格式字符串"""
    return bj_now().strftime(TIME_FORMAT)


def format_local(dt: datetime) -> str:
    """datetime → 存储格式字符串"""
    return dt.strftime(TIME_FORMAT)


def parse_local(s: str) -> datetime | None:
    """存储格式字符串 → 北京时间 datetime；解析失败返回 None"""
    try:
        return datetime.strptime(s, TIME_FORMAT).replace(tzinfo=_bj_tz)
    except ValueError:
        return None


def from_ts(ts) -> datetime | None:
    """Unix 时间戳（秒）→ 北京时间 datetime；缺失/无效返回 None"""
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), _bj_tz)
    except (ValueError, OSError, OverflowError):
        return None
