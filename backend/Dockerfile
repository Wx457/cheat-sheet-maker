# syntax=docker/dockerfile:1
# backend/Dockerfile
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖 (少数 Python 包没有预编译 wheel 时需要 gcc 编译)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖：BuildKit 缓存挂载保留 pip 下载缓存（不进镜像），
# requirements.txt 变动时只下载新增 / 变更的包
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# 复制其余代码
COPY . .

# 暴露端口 (仅作文档声明，实际由 docker-compose 控制)
EXPOSE 8000
