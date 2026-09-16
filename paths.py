# -*- coding: utf-8 -*-
"""统一路径解析（兼容源码运行 / PyInstaller 打包运行）。

- 源码运行：基准 = 项目根（paths.py 的上一级不存在，paths.py 就在根上）
- 打包运行：基准 = sys._MEIPASS（PyInstaller onedir 模式下 = exe旁的 _internal）
所有模块找模型/资源都应基于 base_dir()，不要再各自 __file__ 推算。
"""
import sys
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller 打包后
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def models_dir() -> Path:
    return base_dir() / "models"


def appdata_dir() -> Path:
    """用户数据目录（历史记录/crash.log 等写入型文件）。

    源码运行与打包运行都用 %APPDATA%/voice-translator，
    避免往安装目录（可能无写权限）里写文件。
    """
    import os
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "voice-translator"
