@echo off
rem 阶段4 测试B：打字输入英文合成播放 —— 双击运行
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage4_tts.py --interactive
echo.
pause
