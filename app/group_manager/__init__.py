"""
群管 app（app/group_manager/）

功能（全部组合底层原语）：
- 自动同意入群：订阅 GROUP_REQUEST，按策略（仅授权群）自动 approve
- 入群引导：欢迎语 + 踢人规则 + 链接 + 段位询问（MemberStore 状态机）
- 观察期：入群 N 分钟未发言自动踢出（TaskScheduler + set_group_kick_member）
- 活跃统计：MESSAGE 事件记录最后发言时间
- 命令：/active /tier 查询成员档案

配置：config/group_manager.yml（欢迎语/规则/链接/观察期/自动同意策略）
"""
