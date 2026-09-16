# -*- coding: utf-8 -*-
"""Moonshine 普通话语音识别引擎（默认实现）。

模型：tiny-streaming-zh（34M 参数，ONNX/ORT 格式，纯 CPU 推理）
API 依据 moonshine_voice 0.1.5：
  - 非流式：transcribe_without_streaming() 直接返回 Transcript
  - 流式：start() / add_audio() / stop() + 事件监听器收行文本
"""
import ctypes
import os
import threading
from pathlib import Path

import numpy as np

from stt.base import SttEngine, SttError
from paths import models_dir

# 模型目录：models/moonshine-zh（源码运行=项目根，打包后=_MEIPASS）
MODEL_DIR = models_dir() / "moonshine-zh"


class MoonshineStt(SttEngine):
    def __init__(self, model_dir: Path = MODEL_DIR):
        self.model_dir = Path(model_dir)
        self._transcriber = None
        self._lock = threading.Lock()

    # ---------- 基类接口 ----------
    @staticmethod
    def _preload_shared_ort():
        """先于 moonshine.dll 加载 Python 包的 onnxruntime.dll，把模块名占住。

        背景（闪退 0xc0000374 堆损坏根因）：moonshine.dll 依赖
        onnxruntime.dll（自带 1.23 旧版），而 Python 包的 onnxruntime
        pyd 里静态链接了另一份 ORT 1.30。若 moonshine.dll 先加载，
        进程里会有两份不同版本的 ORT 运行时——各自起线程池、各自
        管理堆，并发推理时互相踩内存 → 随机堆损坏闪退。

        修法：先用 ctypes 加载 capi 目录的 onnxruntime.dll（1.30），
        Windows 加载器按模块名去重，之后 moonshine.dll 的依赖
        onnxruntime.dll 直接复用这份——全进程只剩一个 ORT。
        实测：moonshine 只按序号导入 OrtGetApiBase/
        OrtSessionOptionsAppendExecutionProvider_CPU 两个函数，
        1.30 里都存在，识别结果与自带 1.23 完全一致。
        """
        try:
            import onnxruntime  # noqa: F401  确保 capi 目录在 sys.path 语义内
        except Exception:
            return
        capi = Path(onnxruntime.__file__).parent / "capi"
        dll = capi / "onnxruntime.dll"
        if not dll.exists():
            return
        try:
            os.add_dll_directory(str(capi))
            ctypes.WinDLL(str(dll))
        except OSError:
            pass  # 加载失败就维持原状（moonshine 用自带那份）

    def load(self) -> None:
        self._preload_shared_ort()
        try:
            from moonshine_voice import Transcriber
        except ImportError as e:
            raise SttError(f"moonshine_voice 未安装：{e}")
        if not self.model_dir.exists():
            raise SttError(f"模型目录不存在：{self.model_dir}")
        try:
            from moonshine_voice.moonshine_api import ModelArch
            self._transcriber = Transcriber(
                model_path=str(self.model_dir), model_arch=ModelArch.TINY_STREAMING
            )
        except Exception as e:
            raise SttError(f"模型加载失败：{e}")
        # 预热：跑一遍空识别，消除首次推理的图优化/内存分配开销
        try:
            self.transcribe_file(np.zeros(16000, dtype=np.float32), 16000)
        except Exception:
            pass

    def transcribe_file(self, audio: np.ndarray, sample_rate: int) -> str:
        """非流式：一次性识别一整段音频。"""
        self._ensure_ready()
        audio = self._to_mono_float32(audio)
        try:
            result = self._transcriber.transcribe_without_streaming(
                audio.tolist(), sample_rate
            )
        except Exception as e:
            raise SttError(f"识别失败：{e}")
        return self._join_transcript(result)

    def close(self) -> None:
        if self._transcriber is not None:
            try:
                self._transcriber.close()
            except Exception:
                pass
            self._transcriber = None

    # ---------- 流式接口 ----------
    def supports_streaming(self) -> bool:
        return True

    def start_stream(self) -> None:
        """开始一次流式识别会话，行完成事件会存入内部缓冲。"""
        self._ensure_ready()
        with self._lock:
            self._stream_lines = []
            self._listener_installed = getattr(self, "_listener_installed", False)
            if not self._listener_installed:
                self._transcriber.add_listener(self._on_event)
                self._listener_installed = True
        self._transcriber.start()

    def feed_chunk(self, chunk: np.ndarray, sample_rate: int) -> None:
        self._transcriber.add_audio(self._to_mono_float32(chunk).tolist(), sample_rate)

    def finish_stream(self) -> str:
        """结束会话，返回所有已完成行的合并文本。"""
        self._transcriber.stop()
        with self._lock:
            lines = list(self._stream_lines)
            self._stream_lines = []
        return "".join(lines).strip()

    # ---------- 事件 ----------
    def _on_event(self, event):
        from moonshine_voice.transcriber import LineCompleted

        if isinstance(event, LineCompleted):
            with self._lock:
                self._stream_lines.append(event.line.text)

    # ---------- 内部 ----------
    def _ensure_ready(self):
        if self._transcriber is None:
            raise SttError("引擎未加载，请先调用 load()")

    @staticmethod
    def _to_mono_float32(audio):
        a = np.asarray(audio, dtype=np.float32)
        if a.ndim > 1:
            a = a.mean(axis=1)
        return a

    @staticmethod
    def _join_transcript(transcript) -> str:
        """Transcript 对象 -> 纯文本。"""
        lines = getattr(transcript, "lines", None) or []
        return "".join(getattr(line, "text", "") for line in lines).strip()
