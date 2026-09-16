@echo off
rem 阶段0：环境自检 —— 双击运行这个文件即可
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe scripts\check_env.py
echo.
pause
