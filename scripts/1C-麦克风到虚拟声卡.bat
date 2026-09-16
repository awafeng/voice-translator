@echo off
rem 阶段1 测试B：麦克风录音 -> 播放到虚拟声卡 —— 双击运行
rem 会先列出设备让你选编号，倒数3秒后录5秒
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe scripts\stage1_mic.py
echo.
pause
