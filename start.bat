@echo off
chcp 65001 >nul 2>&1
title YLCraft

echo ========================================
echo  YLCraft 启动脚本
echo ========================================
echo.

cd /d "%~dp0"

REM ========================================
REM 后端初始化
REM ========================================
echo [后端] 检查 Python 虚拟环境...

if not exist backend\venv (
    echo [后端] 虚拟环境不存在，正在创建...
    python -m venv backend\venv
    echo [后端] 虚拟环境创建完成
) else (
    echo [后端] 虚拟环境已存在
)

echo [后端] 安装依赖...
call backend\venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>&1
for %%f in (requirements.txt) do (
    if exist "backend\%%f" pip install -r backend\%%f >nul 2>&1
)
echo [后端] 依赖就绪

REM ========================================
REM 前端初始化
REM ========================================
echo [前端] 检查依赖...
if not exist frontend\node_modules (
    echo [前端] node_modules 不存在，正在安装...
    cd frontend
    call npm install
    cd ..
) else (
    echo [前端] node_modules 已存在
)

REM ========================================
REM 启动服务
REM ========================================
echo.
echo ========================================
echo  启动服务...
echo ========================================

REM 启动后端
start "YLCraft-Backend" cmd /k "cd /d "%~dp0backend" && ..\backend\venv\Scripts\activate.bat && python -m uvicorn app.main:app --reload --port 8000"

REM 等待后端启动
timeout /t 4 /nobreak >nul

REM 启动前端
start "YLCraft-Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo ========================================
echo  YLCraft 已启动！
echo  后端: http://localhost:8000
echo  前端: http://localhost:5173
echo  API文档: http://localhost:8000/docs
echo ========================================
pause
