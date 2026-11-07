@echo off
chcp 65001 >nul
title OnlineExam API Server - 127.0.0.1:8777

rem 被测系统根目录：默认 D:\OnlineExam，可用环境变量 OE_PROJECT 覆盖
if "%OE_PROJECT%"=="" set OE_PROJECT=D:\OnlineExam
cd /d "%OE_PROJECT%"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] venv not found: D:\OnlineExam\.venv\Scripts\python.exe
    pause
    exit /b 1
)

echo ============================================================
echo  OnlineExam dev server
echo  URL : http://127.0.0.1:8777
echo  Env : %CD%\.venv
echo.
echo  Keep this window OPEN while running PyCharm tests.
echo  [WinError 10061] means this window is not running.
echo ============================================================
echo.

.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8777 --noreload

echo.
echo Server stopped.
pause
