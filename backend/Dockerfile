# backend/Dockerfile
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖 (编译某些 Python 包可能需要 gcc, 以及 playwright 依赖)
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    musl-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器内核 (用于生成 PDF)
RUN playwright install chromium
RUN playwright install-deps

# 将前端构建产物复制到镜像中
COPY frontend/dist /app/static

# 复制其余代码
COPY . .

# 暴露端口 (仅作文档声明，实际由 docker-compose 控制)
EXPOSE 8000