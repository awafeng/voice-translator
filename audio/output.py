# -*- coding: utf-8 -*-
"""音频输出层：虚拟声卡输出 + 可选本地回放。

OutputManager 职责：
  - 把合成好的英文音频送到虚拟声卡（CABLE Input）
  - 本地回放开关打开时，同时复制一份到默认扬声器
  - 管理设备名/设备号解析（设备号变化也能按名字找到）
"""
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd


def _norm(name: str) -> str:
    return (name or "").lower()


class OutputManager:
    def __init__(self, cable_keyword: str = "cable",
                 volume: float = 1.0, local_playback: bool = False,
                 output_device: "int | None" = None):
        """
        cable_keyword: 虚拟声卡输出端设备名里包含的关键字
        volume:        发送到虚拟声卡的音量（0.0~1.0）
        local_playback:本地回放开关（True=同时在默认扬声器播放）
        output_device: "输出麦克风"对应的设备号（None=自动找虚拟声卡）。
                       语义：英文语音伪装成用户选的这个"麦克风"。
                       若选的是收音端（CABLE Output），自动映射到同一
                       虚拟声卡的播放端（CABLE Input）去写入。
        """
        self.cable_keyword = cable_keyword.lower()
        self.volume = max(0.0, min(1.0, volume))
        self.local_playback = local_playback
        self.output_device = output_device
        self._lock = threading.Lock()

    # ---------- 设备解析 ----------
    def find_cable_output(self):
        """找到英文语音实际写入的设备号（虚拟声卡的播放端）。

        output_device 语义是"输出麦克风"（Discord 看到的麦克风）：
          - 用户选了虚拟声卡的收音端（如 CABLE Output）→ 写到同一
            虚拟声卡的播放端（CABLE Input）
          - 用户选了真麦克风 → 直接写入该设备（对方听到你的原声，
            用于对比测试；写入收音设备在某些驱动上会被忽略）
          - 未选（None）→ 自动找虚拟声卡播放端
        """
        if self.output_device is not None:
            try:
                name = sd.query_devices(self.output_device)["name"] or ""
            except Exception:
                name = ""
            nl = name.lower()
            is_input_dev = False
            try:
                is_input_dev = sd.query_devices(
                    self.output_device)["max_input_channels"] > 0
            except Exception:
                pass
            if is_input_dev and ("cable" in nl or "vb-audio" in nl):
                # 收音端 → 找同一虚拟声卡的播放端
                for i, d in enumerate(sd.query_devices()):
                    if d["max_output_channels"] > 0 and (
                        "cable" in _norm(d["name"])
                        or "vb-audio" in _norm(d["name"])
                    ):
                        return i
                return None
            # 其他情况按用户选择直写
            return self.output_device
        # 自动模式：找虚拟声卡播放端
        try:
            for i, d in enumerate(sd.query_devices()):
                if d["max_output_channels"] > 0 and (
                    self.cable_keyword in _norm(d["name"])
                    or "vb-audio" in _norm(d["name"])
                ):
                    return i
        except Exception:
            pass
        return None

    def cable_ready(self) -> bool:
        return self.find_cable_output() is not None

    # ---------- 播放 ----------
    def play_to_cable(self, audio: np.ndarray, sr: int) -> None:
        """把音频送到虚拟声卡；本地回放开着时同时送到默认扬声器。"""
        if len(audio) == 0:
            return
        dev = self.find_cable_output()
        sig = (audio * self.volume).astype(np.float32)
        with self._lock:
            if dev is None:
                raise RuntimeError(
                    "未找到虚拟声卡设备（CABLE Input）。请先安装 VB-CABLE。"
                )
            sd.play(sig, sr, device=dev)
            if self.local_playback:
                # 双路播放：声卡线程各播各的，互不阻塞
                threading.Thread(
                    target=self._play_default, args=(sig.copy(), sr), daemon=True
                ).start()
            sd.wait()  # 等虚拟声卡路播完（调用方通常在独立线程）

    def _play_default(self, sig, sr):
        try:
            sd.play(sig, sr)  # 默认设备
            sd.wait()
        except Exception:
            pass

    # ---------- 运行期设置 ----------
    def set_volume(self, v: float):
        self.volume = max(0.0, min(1.0, v))

    def set_local_playback(self, on: bool):
        self.local_playback = bool(on)

    def close(self):
        try:
            sd.stop()
        except Exception:
            pass
