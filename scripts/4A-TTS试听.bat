@echo off
rem 阶段4 测试A：合成4句英文并从默认扬声器播放 —— 双击运行
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage4_tts.py
echo.
pause
