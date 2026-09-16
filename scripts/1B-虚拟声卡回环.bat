@echo off
rem 阶段1 测试A：虚拟声卡回环验证（无需麦克风）—— 双击运行
rem 你会听到两声"叮-咚"从默认扬声器传出
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe scripts\stage1_loopback.py
echo.
pause
