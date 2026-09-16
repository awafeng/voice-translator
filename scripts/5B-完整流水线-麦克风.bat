@echo off
rem 阶段5 测试B：完整流水线（麦克风，需要麦克风）—— 双击运行
rem 倒数3秒后说5秒中文，然后听到英文
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage5_pipeline.py --mic
echo.
pause
