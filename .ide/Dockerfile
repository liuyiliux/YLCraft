# YLCraft 开发环境 Dockerfile
# 包含后端 (Python 3.11 + FastAPI) + 前端 (Node 20 + React/Vite)
# CodeBuddy 工具链已保留

FROM python:3.11-slim

# 安装 Node.js 20 + 编译工具链（faster-whisper 依赖 C++ 编译）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    ffmpeg \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# 验证安装
RUN python3 --version && node --version && npm --version && ffmpeg -version | head -1

# 后端依赖预安装（加速容器启动）
WORKDIR /workspace/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 前端依赖预安装
WORKDIR /workspace/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install

# 工作目录切回项目根
WORKDIR /workspace
