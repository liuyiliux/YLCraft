@echo off
chcp 65001 >nul 2>&1
title YLCraft

echo ========================================
echo  YLCraft 启动脚本 (Windows)
echo ========================================
echo.

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

set "VENV_DIR=backend\venv_win"

REM ========================================
REM 后端初始化
REM ========================================
echo [后端] 检查 Python 虚拟环境...

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    if exist "%VENV_DIR%" (
        echo [后端] 虚拟环境不完整，正在重建...
        rmdir /s /q "%VENV_DIR%"
    ) else (
        echo [后端] 虚拟环境不存在，正在创建...
    )
    python -m venv "%VENV_DIR%"
    echo [后端] 虚拟环境创建完成
) else (
    echo [后端] 虚拟环境已存在
)

echo [后端] 安装依赖...
cd backend
call "%VENV_DIR%\Scripts\activate.bat"
pip install --upgrade pip >nul 2>&1
if exist "requirements.txt" (
    pip install -r requirements.txt >nul 2>&1
)
echo [后端] 依赖就绪
cd ..

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

echo @echo off > "%BASE_DIR%backend\start_backend.bat"
echo cd /d "%BASE_DIR%backend" >> "%BASE_DIR%backend\start_backend.bat"
echo call venv_win\Scripts\activate.bat >> "%BASE_DIR%backend\start_backend.bat"
echo python -m uvicorn app.main:app --reload --port 8000 >> "%BASE_DIR%backend\start_backend.bat"

start "YLCraft-Backend" cmd /k "%BASE_DIR%backend\start_backend.bat"

timeout /t 4 /nobreak >nul

start "YLCraft-Frontend" cmd /k "cd /d ""%BASE_DIR%frontend"" && npm run dev"

echo.
echo ========================================
echo  YLCraft 已启动！
echo  后端: http://localhost:8000
echo  前端: http://localhost:5173
echo  API文档: http://localhost:8000/docs
echo ========================================
pause

del "%BASE_DIR%backend\start_backend.bat" >nul 2>&1