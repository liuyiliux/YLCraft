@echo off
chcp 65001 >nul 2>&1
title YLCraft (hot reload, unstable on Windows)
cd /d "%~dp0"

REM ================================================================
REM  带热更新的后端启动方式 —— 2026-10-07
REM
REM  ⚠️ 用之前先读完这段，你会权衡的：
REM
REM  这个脚本带 `--reload`，也就是 `start.bat` 刻意去掉的那个参数。
REM  在这台机器上，`start.bat` 曾经因此卡死：
REM     启动 → 约 2 秒后崩(WinError 87) → 自动重启 → 再崩
REM  日志里 91 次，"Application startup complete" 0 次，
REM  表现是「端口在监听、但所有请求超时」。
REM
REM  所以：**日常请用 start.bat**（没有 --reload）。这个脚本只在
REM  你确实需要热更新、又愿意自己盯着它别崩的时候用。
REM
REM  如果用了这个脚本又卡住了，Ctrl+C 关掉，改用 start.bat。
REM ================================================================

echo.
echo ========================================
echo  Backend with --reload (hot reload)
echo  Watch the log below for "Accept failed"
echo  If it hangs: Ctrl+C, then use start.bat
echo ========================================
echo.

cd /d "%~dp0backend"
call venv_win\Scripts\activate.bat
python -m uvicorn app.main:app --reload --port 8000 --loop app.core.win_loop:new_loop