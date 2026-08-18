# YLCraft 开发环境 Dockerfile
# 包含后端 (Python 3.11 + FastAPI) + 前端 (Node 20 + React/Vite)
# CodeBuddy 工具链已保留

FROM python:3.11-slim

# 安装 Node.js 20 + python3-venv + 编译工具链（faster-whisper 依赖 C++ 编译）
# 并安装 openssh-server（支持 VSCode 等客户端 Remote-SSH 访问开发环境）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    ffmpeg \
    build-essential \
    python3-venv \
    openssh-server \
    sudo \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# 安装 code-server 及常用 VSCode 插件
# 说明：安装 code-server 后即为「单容器模式」——开发环境与 code-server 在同一容器内运行，
# 无需系统额外拉起一个 code-server 容器（双容器模式）。
RUN curl -fsSL https://code-server.dev/install.sh | sh \
    && code-server --install-extension cnbcool.cnb-welcome \
    && code-server --install-extension redhat.vscode-yaml \
    && code-server --install-extension dbaeumer.vscode-eslint \
    && code-server --install-extension mhutchie.git-graph \
    && echo done

# 验证安装（python / node / ffmpeg / code-server / sshd）
RUN python3 --version && node --version && npm --version && ffmpeg -version | head -1 \
    && code-server --version && which sshd

# 指定字符集支持命令行输入中文
ENV LANG C.UTF-8
ENV LANGUAGE C.UTF-8

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
