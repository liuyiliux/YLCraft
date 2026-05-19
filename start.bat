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

start "YLCraft-Backend" cmd /k "cd /d ""%~dp0backend"" && venv_win\Scripts\activate.bat && python -m uvicorn app.main:app --reload --port 8000"

timeout /t 4 /nobreak >nul

start "YLCraft-Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

echo.
echo ========================================
echo  YLCraft Started!
echo  Backend: http://localhost:8000
echo  Frontend: http://localhost:5173
echo  API Docs: http://localhost:8000/docs
echo ========================================
pause