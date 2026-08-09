# AuroraBot

QQ 机器人：连接 NapCat（OneBot WebSocket），统一命令注册/权限底座，内置权限系统与群管 app。

## 架构

```
NapCat (QQ 客户端 + OneBot WS)  ⇐ws://⇐  AuroraBot (本仓库)
```

- `api/`：WS 连接层 + OneBot API 客户端 + 消息分发
- `app/core/`：命令注册中心 / 事件总线 / 权限底座 / 成员存储 (sqlite) / 热更新
- `app/permission` 归位后位于 `app/core/permission`：权限服务
- `app/Lssuing/`：权限系统命令（订阅/授权/群主等）
- `app/group_manager/`：群管（入群引导/观察期/段位/自动同意入群/不活跃踢人/批量踢人/@全体）

## 本地运行

```bash
uv sync --frozen          # 安装依赖
uv run python main.py     # 启动（需先配置 WS_URL，默认 ws://127.0.0.1:3001）
```

- 环境变量：`AURORA_ENV`（dev/prod，默认 dev）、`WS_URL`（默认读 `config/environment/*.py`）
- 配置：`config/group_manager.yml`（群管配置，可用 `/gm_config` 热改）、`config/_config.yml`（QQ 管理员账号）
- 数据：`store/db/*.db`（成员/权限 sqlite）

## Docker 部署（双容器，NapCat 独立）

```bash
docker compose up -d --build
```

- `aurorabot`：NapCat（QQ 登录态在 `napcat-data` 卷）
- `app`：AuroraBot（`./store`、`./config` 挂载持久化，`WS_URL=ws://aurorabot:3001`）

## Docker 部署（一体化镜像）

NapCat + AuroraBot 打包进同一个镜像，任何 Docker 环境直接挂载使用：

```bash
# 构建
docker build -f Dockerfile.allinone -t aurora-bot:allinone .

# 运行（挂载数据卷持久化；Windows PowerShell 请用反引号续行或直接复制单行）
docker run -d --name aurora-allinone \
  --restart unless-stopped \
  -p 6099:6099 -p 6081:6081 -p 3001:3001 \
  -v aurora-napcat:/app/.config/QQ \
  -v aurora-store:/app/bot/store \
  -v aurora-config:/app/bot/config \
  aurora-bot:allinone

# Windows PowerShell 单行等价：
# docker run -d --name aurora-allinone --restart unless-stopped -p 6099:6099 -p 6081:6081 -p 3001:3001 -v aurora-napcat:/app/.config/QQ -v aurora-store:/app/bot/store -v aurora-config:/app/bot/config aurora-bot:allinone
```

- 容器内 supervisord 同时管理 `qq`（NapCat）与 `bot` 两个进程
- bot 自动连接容器内 `ws://127.0.0.1:3001`
- **首次启动**：打开 WebUI `http://<host>:6099` 扫码登录 QQ；登录后在 WebUI 启用 WebSocket 服务器端口 3001（参考 `config/nt_config/onebot11_*.json`），bot 即自动连上
- 端口：`6099` NapCat WebUI、`6081` noVNC 桌面、`3001` OneBot WS（供外部工具）
- 卷：`aurora-napcat` QQ 登录态、`aurora-store` bot 数据库、`aurora-config` bot 配置

## 命令

`/help` 英文命令帮助、`/菜单` 中文命令菜单（`/菜单 <命令>` 查看详情，中文命令与英文命令等价，如 `/踢人` 同 `/kick`）。权限分级：系统管理员 > 群主/付费用户 > 群管理员 > 所有用户。

## 测试

```bash
uv run python test/test_commands.py   # 等各测试文件
```
