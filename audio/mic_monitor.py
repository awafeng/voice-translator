# -*- coding: utf-8 -*-
"""输入麦克风电平监视（仅供界面"输入音量"条显示，不参与翻译）。

独立开一路只读音频流，实时计算音量；翻译引擎运行时会暂停
（麦克风由引擎占用），由引擎的采集回调接续更新电平。
"""
import threading

import numpy as np
import sounddevice as sd


class MicLevelMonitor:
    def __init__(self, block_ms: int = 60):
        self._block_ms = block_ms
        self._level = 0.0        # 最近一块的 RMS（0~1）
        self._lock = threading.Lock()
        self._stream = None
        self._device = "unstarted"

    def start(self, device=None):
        """在指定设备上开始监视。多种参数组合回退，尽量打开真实麦克风。
        start() 也放进回退循环（WASAPI 设备可能 open 成功但 start 报
        UNSUPPORTED_FORMAT）。全部失败保持关闭（音量条 0，不报错）。"""
        self.stop()
        self._device = device
        try:
            dev_sr = int(sd.query_devices(device)["default_samplerate"] or 16000)
        except Exception:
            dev_sr = 16000
        try:
            dev_ch = int(sd.query_devices(device)["max_input_channels"] or 1)
        except Exception:
            dev_ch = 1
        for sr, ch, dt in ((16000, 1, "float32"), (dev_sr, 1, "float32"),
                           (dev_sr, min(2, dev_ch), "float32"),
                           (16000, 1, "int16"), (dev_sr, 1, "int16"),
                           (dev_sr, min(2, dev_ch), "int16")):
            stream = None
            try:
                stream = sd.InputStream(
                    device=device, samplerate=sr, channels=ch,
                    blocksize=max(1, int(sr * self._block_ms / 1000)),
                    dtype=dt, callback=self._cb)
                stream.start()
                self._stream = stream
                return
            except Exception:
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass
                self._stream = None
        # 全部失败：保持关闭（音量条显示 0，不报错不打扰）

    def maybe_restart(self, device):
        """设备变化时才重启监视流（避免每次轮询都重开音频流）。"""
        if device != self._device and self._stream is None:
            self.start(device)

    def _cb(self, indata, frames, t, status):
        a = indata
        if a.dtype.name == "int16":
            a = a.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(a ** 2)))
        with self._lock:
            # 取峰值：短促语音也能顶起来，配合 decay 平滑回落
            self._level = max(rms, self._level)

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    @property
    def level(self) -> float:
        with self._lock:
            return self._level

    def decay(self, factor: float = 0.6):
        """UI 轮询时调用：让电平自然回落。"""
        with self._lock:
            self._level *= factor
