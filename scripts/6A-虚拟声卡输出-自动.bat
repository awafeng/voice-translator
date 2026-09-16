@echo off
rem 阶段6 测试A：流水线输出到虚拟声卡（模拟语音，无需麦克风）—— 双击运行
rem 运行中会问：要不要开本地回放（想从耳机听英文就输 y）
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage6_cable_output.py
echo.
pause
