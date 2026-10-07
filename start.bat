@echo off
chcp 65001 >nul 2>&1
title YLCraft

echo ========================================
echo  YLCraft Start Script (Windows)
echo ========================================
echo.

cd /d "%~dp0"

set "VENV_DIR=backend\venv_win"
set "REQUIREMENTS_FILE=backend\requirements.txt"

REM ========================================
REM Check if using remote database
REM ========================================
set "USE_REMOTE_DB=no"
if exist "backend\.env" (
    findstr /C:"localhost" "backend\.env" >nul
    if errorlevel 1 (
        echo [Config] Remote database detected in .env
        set "USE_REMOTE_DB=yes"
    )
)

REM ========================================
REM Docker Compose - PostgreSQL ^& Redis (skip if using remote)
REM ========================================
if "%USE_REMOTE_DB%"=="yes" (
    echo [Docker] Skipping local Docker ^(using remote database^)
) else (
    echo [Docker] Checking Docker Compose services...
    docker compose version >nul 2>&1
    if errorlevel 1 (
        echo [Docker] Docker Compose not found, please install Docker Desktop
        echo [Docker] Skipping database services...
    ) else (
        echo [Docker] Starting PostgreSQL and Redis...
        docker compose up -d
        echo [Docker] Waiting for PostgreSQL to be ready...
        :wait_loop
        docker compose exec -T postgres pg_isready -U ylcraft >nul 2>&1
        if errorlevel 1 (
            timeout /t 1 /nobreak >nul
            goto wait_loop
        )
        echo [Docker] PostgreSQL is ready!
    )
)

REM ========================================
REM Backend Setup
REM ========================================
echo [Backend] Checking Python virtual environment...

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    if exist "%VENV_DIR%" (
        echo [Backend] Virtual environment incompatible, recreating...
        rmdir /s /q "%VENV_DIR%"
    ) else (
        echo [Backend] Virtual environment not found, creating...
    )
    python -m venv "%VENV_DIR%"
    echo [Backend] Virtual environment created
    echo [Backend] Installing dependencies...
    call "%VENV_DIR%\Scripts\activate.bat"
    pip install --upgrade pip >nul 2>&1
    if exist "%REQUIREMENTS_FILE%" (
        pip install -r "%REQUIREMENTS_FILE%"
    )
    echo [Backend] Dependencies installed
) else (
    echo [Backend] Virtual environment exists
    echo [Backend] Checking and updating dependencies...
    call "%VENV_DIR%\Scripts\activate.bat"
    pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    if exist "%REQUIREMENTS_FILE%" (
        pip install -r "%REQUIREMENTS_FILE%" -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    )
    echo [Backend] Dependencies ready
)

REM ========================================
REM Database Migration
REM ========================================
if exist "backend\.env" (
    echo [Database] Running Alembic migrations...
    cd /d "%~dp0backend"
    call venv_win\Scripts\activate.bat
    alembic upgrade head
    if errorlevel 1 (
        echo [Database] Migration failed, please check database connection
    ) else (
        echo [Database] Migrations completed!
    )
    cd /d "%~dp0"
) else (
    echo [Database] .env not found, skipping migrations
)

REM ========================================
REM Frontend Setup
REM ========================================
echo [Frontend] Checking dependencies...
if not exist frontend\node_modules (
    echo [Frontend] node_modules not found, installing...
    cd frontend
    call npm install
    cd ..
) else (
    echo [Frontend] node_modules exists
)

REM ========================================
REM Start Services
REM ========================================
echo.
echo ========================================
echo  Starting Services...
echo ========================================

REM ⚠️⚠️ **不要加 --reload**（2026-10-07 改）
REM
REM 现象：日志里 91 次 WinError 87，**每次都在启动后约 2 秒**，
REM       且 "Application startup complete" 一行都没出现过
REM       ⇒ 后端卡在「启动 → 崩 → 重启」死循环，端口在监听但不响应。
REM
REM 为什么 --reload 是元凶（**已核对 uvicorn 0.46.0 源码**，不是猜）：
REM     uvicorn/config.py
REM         @property
REM         def use_subprocess(self) -> bool:
REM             return bool(self.reload or self.workers > 1)
REM     → 带 --reload 时 use_subprocess=True，而
REM       uvicorn/loops/asyncio.py 只在 **没开** use_subprocess 时才给
REM       ProactorEventLoop，否则一律 SelectorEventLoop
REM     → SelectorEventLoop 在 Windows 上无法创建子进程，
REM       Patchright 起浏览器会挂，于是重启循环一触即发。
REM
REM 代价：改后端代码后要**手动重启后端窗口**（Ctrl+C 再重开这个窗口）。
REM       这点不便是有意的 —— 换来的是后端不再自己重启到死。
REM       想留着热更新又怕崩，见 start_no_reload.bat 的说明。
REM
REM --loop 仍然保留：它显式给出 ProactorEventLoop，与 --reload 无关，
REM 也是 Patchright 能起浏览器的硬前提（详见 app/core/win_loop.py）。
start "YLCraft-Backend" cmd /k "cd /d ""%~dp0backend"" && venv_win\Scripts\activate.bat && python -m uvicorn app.main:app --port 8000 --loop app.core.win_loop:new_loop"

REM 启动后自检：端口起来但 /health 不通 = 又进了死循环，直接告诉你
REM（以前只能等你在页面上点半天才发现）。失败时给出可复制的排查命令。
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Sleep -Seconds 12; try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 8 'http://127.0.0.1:8000/health'; if ($r.StatusCode -eq 200) { Write-Host '  [Backend] OK - http://localhost:8000' -ForegroundColor Green } } catch { Write-Host ''; Write-Host '  [Backend] 启动失败或无响应！' -ForegroundColor Red; Write-Host '  最常见：8000 端口被旧进程占着' -ForegroundColor Yellow; Write-Host '  排查： netstat -ano | findstr :8000   然后 taskkill /PID <PID> /F' -ForegroundColor Yellow; Write-Host '  看崩溃现场： backend\storage\logs\app.log 里搜 Accept failed' -ForegroundColor Yellow }"

timeout /t 4 /nobreak >nul

start "YLCraft-Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

echo.
echo ========================================
echo  YLCraft Started!
echo  Backend: http://localhost:8000
echo  Frontend: http://localhost:3000
echo  API Docs: http://localhost:8000/docs
echo ========================================
pause