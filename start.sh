#!/usr/bin/env bash
# ============================================================
#  YLCraft 启动脚本 (Linux/macOS)
#  对应 Windows 版本的 start.bat
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 子进程 PID 记录（用于优雅退出）
BACKEND_PID=""
FRONTEND_PID=""

# 退出时清理子进程
cleanup() {
    echo ""
    echo -e "${YELLOW}[YLCraft] 正在停止服务...${NC}"
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null || true
        echo -e "${GREEN}[后端] 已停止 (PID: $BACKEND_PID)${NC}"
    fi
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill "$FRONTEND_PID" 2>/dev/null || true
        echo -e "${GREEN}[前端] 已停止 (PID: $FRONTEND_PID)${NC}"
    fi
    echo -e "${CYAN}[YLCraft] 再见！${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

echo -e "${CYAN}========================================"
echo "  YLCraft 启动脚本"
echo -e "========================================${NC}"
echo ""

# ========================================
# 检查依赖
# ========================================
check_command() {
    if ! command -v "$1" &>/dev/null; then
        echo -e "${RED}[错误] 未找到 $1，请先安装后再运行${NC}"
        exit 1
    fi
}

check_command python3
check_command node

# ========================================
# 后端初始化
# ========================================
echo -e "${CYAN}[后端]${NC} 检查 Python 虚拟环境..."

# 检查 venv 是否存在且完整（有 activate 脚本和 pip）
VENV_OK=true
if [ ! -f "backend/venv/bin/activate" ] || [ ! -f "backend/venv/bin/pip" ]; then
    VENV_OK=false
fi

if [ "$VENV_OK" = true ]; then
    echo -e "${GREEN}[后端]${NC} 虚拟环境已存在"
else
    if [ -d "backend/venv" ]; then
        echo -e "${YELLOW}[后端]${NC} 虚拟环境不完整，正在重建..."
        rm -rf backend/venv
    else
        echo -e "${YELLOW}[后端]${NC} 虚拟环境不存在，正在创建..."
    fi
    python3 -m venv backend/venv
    echo -e "${GREEN}[后端]${NC} 虚拟环境创建完成"
fi

echo -e "${CYAN}[后端]${NC} 安装依赖..."
source backend/venv/bin/activate
pip install --upgrade pip -q
if [ -f "backend/requirements.txt" ]; then
    pip install -r backend/requirements.txt -q
fi
echo -e "${GREEN}[后端]${NC} 依赖就绪"

# 检查 .env 文件
if [ ! -f "backend/.env" ] && [ -f "backend/.env.example" ]; then
    echo -e "${YELLOW}[后端]${NC} 未找到 .env 文件，已从 .env.example 复制，请修改 API Key"
    cp backend/.env.example backend/.env
fi

# ========================================
# 前端初始化
# ========================================
echo -e "${CYAN}[前端]${NC} 检查依赖..."
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}[前端]${NC} node_modules 不存在，正在安装..."
    cd frontend
    npm install
    cd "$SCRIPT_DIR"
else
    echo -e "${GREEN}[前端]${NC} node_modules 已存在"
fi

# ========================================
# 启动服务
# ========================================
echo ""
echo -e "${CYAN}========================================"
echo "  启动服务..."
echo -e "========================================${NC}"

# 启动后端
cd "$SCRIPT_DIR/backend"
source venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
echo -e "${GREEN}[后端]${NC} 已启动 (PID: $BACKEND_PID)"

# 等待后端启动
sleep 3

# 启动前端
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!
echo -e "${GREEN}[前端]${NC} 已启动 (PID: $FRONTEND_PID)"

echo ""
echo -e "${CYAN}========================================"
echo "  YLCraft 已启动！"
echo "  后端: http://localhost:8000"
echo "  前端: http://localhost:5173"
echo "  API文档: http://localhost:8000/docs"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo -e "========================================${NC}"

# 等待任一子进程退出
wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || wait