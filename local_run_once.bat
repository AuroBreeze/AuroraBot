@echo off
rem 使用 uv 创建虚拟环境并安装依赖（首次运行）
rem 默认不含未挂载 app 的重依赖；启用 Commodity_lssuing/Proxy_talk 时改为: uv sync --extra full
uv sync

rem 启动
uv run python main.py
