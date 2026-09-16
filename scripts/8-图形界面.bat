@echo off
rem 图形界面（网页版 UI，WebView2 渲染）—— 双击运行
chcp 65001 >nul
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 gui\web_app.py
echo.
pause
