@echo off
rem 一键下载所有模型（约 146MB，国内网络自动走镜像）
cd /d "%~dp0.."
if not exist venv\Scripts\python.exe (
  echo [!] 没找到 venv 虚拟环境。请先按 README 安装依赖。
  pause
  exit /b 1
)
venv\Scripts\python.exe scripts\下载模型.py
pause
