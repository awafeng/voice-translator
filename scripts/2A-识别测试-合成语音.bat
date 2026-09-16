@echo off
rem 阶段2 测试A：用合成中文语音测试识别（无需麦克风）—— 双击运行
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage2_stt.py
echo.
pause
