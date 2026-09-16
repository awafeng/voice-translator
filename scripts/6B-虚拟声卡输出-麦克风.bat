@echo off
rem 阶段6 测试B：麦克风录音 → 流水线 → 虚拟声卡（需要麦克风）—— 双击运行
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage6_cable_output.py --mic
echo.
pause
