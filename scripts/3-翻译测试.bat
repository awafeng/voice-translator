@echo off
rem 阶段3：机器翻译测试 —— 双击运行
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 scripts\stage3_translate.py
echo.
pause
