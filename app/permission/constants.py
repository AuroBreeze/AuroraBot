"""权限核心常量"""

# 权限级别：数字越小权限越高
LEVEL_SYSTEM = 1   # 系统管理员（多管理员表 admin_users）
LEVEL_OWNER = 2    # 群主 / 付费用户
LEVEL_ADMIN = 3    # 群管理员

# 未授权 / 无记录的兜底级别（大于所有有效级别）
LEVEL_NONE = 4

# 时间格式（统一存储与比较格式）
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
