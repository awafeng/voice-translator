@echo off
rem 阶段7 测试B：实时翻译（需要麦克风）—— 双击运行
rem 说一句中文，停顿约半秒，英文自动出。按回车停止。
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage7_latency.py --mic
echo.
pause
