@echo off
rem 阶段1 工具：列出本机所有音频设备 —— 双击运行
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe scripts\list_devices.py
echo.
pause
