# -*- coding: utf-8 -*-
"""翻译历史存储（追加式 JSONL，每行一条，防崩溃丢全库）。

设计：
  - 数据文件放用户目录（%APPDATA%/voice-translator/history.jsonl），
    不放项目目录——打包成 exe 后项目目录可能是只读的
  - 只存文字 + 时间戳 + 延迟（不存音频，符合文档要求）
  - 追加写 + 每次刷新内存缓存，读取走缓存
  - 上限保护：超过 max_entries 条自动裁掉最旧的（默认 1 万条，约 2MB）
"""
import json
import os
import threading
import time
from pathlib import Path


def _default_dir() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    d = Path(base) / "voice-translator"
    d.mkdir(parents=True, exist_ok=True)
    return d


class HistoryStore:
    def __init__(self, max_entries: int = 10000, data_dir: Path | None = None):
        self.max_entries = max_entries
        self.data_dir = Path(data_dir) if data_dir else _default_dir()
        self.path = self.data_dir / "history.jsonl"
        self._lock = threading.Lock()
        self._entries = self._load_all()

    # ---------- 读取 ----------
    def _load_all(self):
        if not self.path.exists():
            return []
        entries = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue  # 跳过损坏行，不崩
        except Exception:
            return []
        return entries

    def get_recent(self, limit: int = 100):
        """最近的 limit 条（新在前）。"""
        with self._lock:
            return list(reversed(self._entries[-limit:]))

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    # ---------- 写入 ----------
    def add(self, zh: str, en: str, delay_ms: float | None = None) -> None:
        """记录一条翻译。字段齐全但保持精简。"""
        rec = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ts": time.time(),
            "zh": zh,
            "en": en,
        }
        if delay_ms is not None:
            rec["delay_ms"] = round(delay_ms, 0)
        with self._lock:
            self._entries.append(rec)
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception:
                pass  # 磁盘满/权限问题不阻塞翻译主流程
            # 上限裁剪（重新写文件，低频操作可接受）
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries:]
                try:
                    tmp = self.path.with_suffix(".tmp")
                    with open(tmp, "w", encoding="utf-8") as f:
                        for e in self._entries:
                            f.write(json.dumps(e, ensure_ascii=False) + "\n")
                    os.replace(tmp, self.path)
                except Exception:
                    pass

    # ---------- 管理 ----------
    def clear(self) -> None:
        with self._lock:
            self._entries = []
            try:
                self.path.unlink(missing_ok=True)
            except Exception:
                pass
