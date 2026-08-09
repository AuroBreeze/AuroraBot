#!/bin/bash

# Docker 自动清理脚本
# 清理内容：退出容器、悬挂卷、未用镜像、构建缓存、日志

LOG_TAG="[DOCKER-CLEANUP]"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $LOG_TAG === 开始 Docker 清理 ==="

# 1. 清除已退出的容器
docker container prune -f
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $LOG_TAG 已清除已退出容器"

# 2. 清除未使用的镜像
docker image prune -af
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $LOG_TAG 已清除未使用的镜像"

# 3. 清除未挂载的 volume
docker volume prune -f
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $LOG_TAG 已清除悬空卷"

# 4. 清除未使用的网络
docker network prune -f
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $LOG_TAG 已清除未使用网络"

# 5. 清除构建缓存
docker builder prune -af
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $LOG_TAG 已清除构建缓存"

# 6. 清空所有容器日志文件
find /var/lib/docker/containers/ -type f -name "*.log" -exec truncate -s 0 {} \;
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $LOG_TAG 所有容器日志已清空"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] $LOG_TAG === Docker 清理完成 ==="
