# -*- coding: utf-8 -*-
"""全局快捷键模块（keyboard 库，Windows 全局钩子）。

设计：
  - HotkeyManager 独立于 GUI，回调通知"开/关切换"
  - 默认 Ctrl+Alt+T（Toggle），可在设置里改（注册前先解除旧绑定）
  - 快捷键触发 -> 回调 -> GUI 同步状态（阶段9 要求"界面状态同步更新"）

锁的约定（修复过死锁）：
  - 只有公开方法 register/unregister/set_hotkey/close 拿 self._lock
  - 内部方法 _register_locked/_unregister_locked 不拿锁
  - 绝不允许"拿着锁再调一个会拿锁的方法"（曾导致界面线程死锁）
"""
import threading


class HotkeyManager:
    def __init__(self, on_toggle, default_hotkey: str = "ctrl+alt+t"):
        """
        on_toggle: 无参回调，快捷键按下时调用（在 keyboard 线程里，
                   GUI 里应转投 UI 线程执行）
        default_hotkey: keyboard 库格式的组合键，如 "ctrl+alt+t"
        """
        self.on_toggle = on_toggle
        self.hotkey = default_hotkey
        self._registered = False
        self._lock = threading.Lock()

    # ───────────────── 公开方法（加锁） ─────────────────
    def set_hotkey(self, combo: str) -> bool:
        """改绑快捷键。成功返回 True，格式非法返回 False。"""
        combo = (combo or "").strip().lower()
        if not combo:
            return False
        with self._lock:
            self._unregister_locked()
            self.hotkey = combo
            return self._register_locked()

    def register(self) -> bool:
        """注册当前快捷键。"""
        with self._lock:
            return self._register_locked()

    def unregister(self):
        with self._lock:
            self._unregister_locked()

    def close(self):
        with self._lock:
            self._unregister_locked()

    # ───────────────── 内部方法（不拿锁） ─────────────────
    def _register_locked(self) -> bool:
        try:
            import keyboard
        except ImportError:
            return False
        self._unregister_locked()
        try:
            keyboard.add_hotkey(
                self.hotkey, self._fire,
                suppress=False,   # 不吞按键：游戏里这个组合键仍然正常
                trigger_on_release=False,
            )
            self._registered = True
            return True
        except Exception:
            self._registered = False
            return False

    def _unregister_locked(self):
        if not self._registered:
            return
        try:
            import keyboard
            keyboard.remove_hotkey(self.hotkey)
        except Exception:
            try:
                import keyboard
                keyboard.unhook_all()  # 兜底：清不掉就全清（我们只注册这一个）
            except Exception:
                pass
        self._registered = False

    def _fire(self):
        try:
            self.on_toggle()
        except Exception:
            pass
