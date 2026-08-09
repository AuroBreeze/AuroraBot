# 阿里云镜像示例
FROM python:3.12-slim

# 时区：容器内统一北京时间（与代码 TIMEZONE 一致）
ENV TZ=Asia/Shanghai \
    AURORA_ENV=prod

WORKDIR /app

# 安装 uv（走阿里云镜像）
RUN pip install --no-cache-dir uv -i https://mirrors.aliyun.com/pypi/simple/

# 先复制依赖清单，利用构建缓存
COPY pyproject.toml uv.lock ./

# 仅安装依赖（项目本体稍后再装，避免源码变更导致缓存失效）
# 默认不含未挂载 app 的重依赖；启用 Commodity_lssuing/Proxy_talk 时改为:
#   RUN uv sync --frozen --no-install-project --extra full
RUN uv sync --frozen --no-install-project

COPY . .

RUN mkdir -p /app/store/db

# 可编辑安装项目本体
RUN uv sync --frozen

# bot 是 WebSocket 客户端（连接 NapCat），无需对外暴露端口；
# 如 NapCat 在同一 compose 网络内，通过服务名访问（见 docker-compose.yml WS_URL）
# EXPOSE 3001

CMD ["uv", "run", "python", "main.py"]
