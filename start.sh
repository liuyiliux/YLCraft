#!/usr/bin/env bash
# ============================================================
#  YLCraft 启动脚本 (Linux/macOS)
#  对应 Windows 版本的 start.bat
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

BACKEND_PID=""
FRONTEND_PID=""

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
# Docker Compose - PostgreSQL & Redis
# ========================================
echo -e "${CYAN}[Docker]${NC} 检查 Docker Compose 服务..."

if command -v docker &>/dev/null && command -v docker compose &>/dev/null; then
    echo -e "${CYAN}[Docker]${NC} 启动 PostgreSQL 和 Redis..."
    docker compose up -d
    
    echo -e "${CYAN}[Docker]${NC} 等待 PostgreSQL 就绪..."
    until docker compose exec -T postgres pg_isready -U ylcraft &>/dev/null; do
        sleep 1
    done
    echo -e "${GREEN}[Docker]${NC} PostgreSQL 已就绪！"
else
    echo -e "${YELLOW}[Docker]${NC} Docker Compose 未找到，请安装 Docker Desktop"
    echo -e "${YELLOW}[Docker]${NC} 跳过数据库服务..."
fi

# ========================================
# Backend Setup
# ========================================
VENV_DIR="backend/venv_linux"

check_command() {
    if ! command -v "$1" &>/dev/null; then
        echo -e "${RED}[错误] 未找到 $1，请先安装后再运行${NC}"
        exit 1
    fi
}

check_command python3
check_command node

# 选择支持 venv 模块的 Python 版本
PYTHON_CMD="python3"
VENV_CREATOR="python3 -m venv"
if ! python3 -m venv --help &>/dev/null; then
    if command -v python3.13 &>/dev/null && python3.13 -m venv --help &>/dev/null; then
        PYTHON_CMD="python3.13"
        echo -e "${YELLOW}[后端]${NC} python3 缺少 venv 模块，使用 python3.13 代替"
    elif command -v python3.11 &>/dev/null && python3.11 -m venv --help &>/dev/null; then
        PYTHON_CMD="python3.11"
        echo -e "${YELLOW}[后端]${NC} python3 缺少 venv 模块，使用 python3.11 代替"
    elif command -v virtualenv &>/dev/null; then
        VENV_CREATOR="virtualenv"
        echo -e "${YELLOW}[后端]${NC} venv 模块不可用，使用 virtualenv 代替"
    else
        echo -e "${RED}[错误] 未找到支持 venv 的 Python 版本，请安装 python3-venv 包或 virtualenv${NC}"
        exit 1
    fi
fi

echo -e "${CYAN}[后端]${NC} 检查 Python 虚拟环境..."

VENV_OK=true
if [ ! -f "$VENV_DIR/bin/activate" ] || [ ! -f "$VENV_DIR/bin/pip" ]; then
    VENV_OK=false
fi

if [ "$VENV_OK" = true ]; then
    echo -e "${GREEN}[后端]${NC} 虚拟环境已存在"
else
    if [ -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}[后端]${NC} 虚拟环境不完整，正在重建..."
        rm -rf "$VENV_DIR"
    else
        echo -e "${YELLOW}[后端]${NC} 虚拟环境不存在，正在创建..."
    fi
    $VENV_CREATOR "$VENV_DIR"
    echo -e "${GREEN}[后端]${NC} 虚拟环境创建完成"
fi

echo -e "${CYAN}[后端]${NC} 安装依赖..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
if [ -f "backend/requirements.txt" ]; then
    pip install -r backend/requirements.txt -q
fi
echo -e "${GREEN}[后端]${NC} 依赖就绪"

if [ ! -f "backend/.env" ] && [ -f "backend/.env.example" ]; then
    echo -e "${YELLOW}[后端]${NC} 未找到 .env 文件，已从 .env.example 复制，请修改 API Key"
    cp backend/.env.example backend/.env
fi

# ========================================
# Database Migration (Alembic)
# ========================================
if [ -f "backend/.env" ]; then
    echo -e "${CYAN}[数据库]${NC} 运行 Alembic 迁移..."
    cd "$SCRIPT_DIR/backend"
    source "$SCRIPT_DIR/$VENV_DIR/bin/activate"
    if alembic upgrade head; then
        echo -e "${GREEN}[数据库]${NC} 迁移完成！"
    else
        echo -e "${RED}[数据库]${NC} 迁移失败，请检查数据库连接"
    fi
    cd "$SCRIPT_DIR"
else
    echo -e "${YELLOW}[数据库]${NC} .env 未找到，跳过迁移"
fi

echo -e "${CYAN}[前端]${NC} 检查依赖..."
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}[前端]${NC} node_modules 不存在，正在安装..."
    cd frontend
    npm install
    cd "$SCRIPT_DIR"
else
    echo -e "${GREEN}[前端]${NC} node_modules 已存在"
fi

echo ""
echo -e "${CYAN}========================================"
echo "  启动服务..."
echo -e "========================================${NC}"

cd "$SCRIPT_DIR/backend"
source "$SCRIPT_DIR/$VENV_DIR/bin/activate"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo -e "${GREEN}[后端]${NC} 已启动 (PID: $BACKEND_PID)"

sleep 3

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
echo "  PostgreSQL: localhost:5432"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo -e "========================================${NC}"

wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || wait