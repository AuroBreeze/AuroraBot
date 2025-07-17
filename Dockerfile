# 阿里云镜像示例
FROM python:3.10.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

COPY . .

RUN mkdir -p /app/store/db


RUN pip install -e .

EXPOSE 3001


CMD ["python","main.py"]
