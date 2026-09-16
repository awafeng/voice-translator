@echo off
rem 阶段2 测试B：用麦克风录音测试识别（需要麦克风）—— 双击运行
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage2_stt.py --mic
echo.
pause
