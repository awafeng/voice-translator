@echo off
rem 阶段7 测试A：延迟基准测试（自动模式，无需麦克风）—— 双击运行
rem 三句模拟语音走完整实时流水线，最后给出端到端延迟数据
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage7_latency.py --bench
echo.
pause
