@echo off
rem 英译中版本图形界面（你说英文，对方听到中文）
cd /d "%~dp0.."
venv\Scripts\python.exe gui\app.py --en2zh
