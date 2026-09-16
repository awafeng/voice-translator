@echo off
rem 阶段5 测试A：完整流水线（模拟语音，无需麦克风）—— 双击运行
rem 你会听到三句"中文进去、英文出来"的完整演示
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage5_pipeline.py
echo.
pause
