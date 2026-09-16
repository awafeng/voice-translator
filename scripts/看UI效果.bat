@echo off
rem 直接运行源码版图形界面（不打包）——改 UI 后看效果用
cd /d "%~dp0.."
venv\Scripts\python.exe gui\app.py
