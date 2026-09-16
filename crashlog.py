# -*- coding: utf-8 -*-
"""崩溃日志：让"莫名闪退"留下线索。

挂在程序入口：
  import crashlog
  crashlog.install()

做的事：
  1. sys.excepthook —— 未捕获 Python 异常写日志
  2. threading.excepthook —— 子线程未捕获异常写日志（GUI 有大量后台线程）
  3. faulthandler —— 原生崩溃（访问违例/堆损坏被启用时）把 Python
     各线程栈 dump 到日志。原生崩溃本身仍会闪退（这是进程级行为），
     但日志里能看到"崩在哪个调用"。

日志位置：%APPDATA%/voice-translator/crash.log（追加写，保留最近 1MB）
"""
import faulthandler
import sys
import threading
import time
import traceback
from pathlib import Path

MAX_LOG_BYTES = 1_000_000


def _log_path() -> Path:
    from paths import appdata_dir
    return appdata_dir() / "crash.log"


def _append(text: str):
    try:
        p = _log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        # 超限则从头截断（保留后半段）
        if p.exists() and p.stat().st_size > MAX_LOG_BYTES:
            data = p.read_text(encoding="utf-8", errors="replace")
            p.write_text(data[len(data) // 2:], encoding="utf-8")
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"\n===== [{stamp}] =====\n{text}\n")
    except Exception:
        pass  # 日志失败不能二次伤害


def _fmt_exception(exc) -> str:
    return "".join(traceback.format_exception(
        type(exc), exc, exc.__traceback__))


def install():
    # 原生崩溃时把所有线程的 Python 栈 dump 出来（frozen 下也能用）
    try:
        f = open(_log_path(), "a", encoding="utf-8")
        faulthandler.enable(file=f)
        # 常驻持有 f；进程生命周期内有效
        _keep = f  # noqa: F841
    except Exception:
        pass

    def _hook(tp, val, tb):
        _append("未捕获异常（主线程）:\n" + _fmt_exception(val))

    sys.excepthook = _hook

    def _thread_hook(args):
        name = getattr(args.thread, "name", "thread") or "thread"
        _append(f"未捕获异常（线程 {name}）:\n" + _fmt_exception(args.exc_value))

    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_hook
