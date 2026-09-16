# -*- coding: utf-8 -*-
"""实时引擎：麦克风流 → VAD 分段 → STT → 翻译 → TTS → 虚拟声卡。

设计与延迟要点：
  - 采集线程（sounddevice 回调）零阻塞，只往队列塞音频
  - VAD/流水线在独立线程跑：一句话结束（静音 600ms）立即处理
  - 处理期间采集不中断（你在说的下一句已在缓存），说完立即接上
  - "感知延迟" = 句尾静音判定时间 + STT + MT + TTS + 播放启动
"""
import queue
import threading
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from audio.output import OutputManager
from audio.pipeline import TranslationPipeline
from history.store import HistoryStore
from vad import SileroVad, VoiceSegmenter

MIC_SR = 16000
BLOCK_MS = 32  # 512 samples @16k = 一帧，与 VAD 对齐


def _candidate_input_devices(device):
    """要依次尝试的输入设备号：指定设备优先，其后追加分发的同名设备。

    同一块物理麦克风会在多个 Host API（MME / DirectSound / WASAPI /
    WDM-KS）下各注册一条【同名】设备；WASAPI 共享模式让系统音频引擎
    自动重采样、最容易打开，排最前；WDM-KS 是裸内核流、只认硬件原生
    采样率/位宽，排最后。
    """
    if device is None:
        return [None]
    try:
        pref = {"windows wasapi": 0, "mme": 1,
                "windows directsound": 2, "windows wdm-ks": 3}
        devs = sd.query_devices()
        name = devs[device]["name"]
        others = []
        for i, d in enumerate(devs):
            if i == device or d["max_input_channels"] <= 0:
                continue
            if d["name"] != name:
                continue
            api = sd.query_hostapis(d["hostapi"])["name"].lower()
            others.append((pref.get(api, 1), i))
        others.sort()
        return [device] + [i for _, i in others]
    except Exception:
        return [device]


class LiveEngine:
    def __init__(self, pipeline: TranslationPipeline, output: OutputManager,
                 input_device: Optional[int] = None,
                 vad_threshold: float = 0.35, silence_ms: int = 450,
                 max_seg_s: float = 12.0, min_seg_s: float = 0.4,
                 speed: float = 1.0, debug: bool = False,
                 on_event: Optional[Callable] = None,
                 use_mic: bool = True,
                 history: "HistoryStore | None" = None):
        self.pipe = pipeline
        self.out = output
        self.input_device = input_device
        self.debug = debug
        self.speed = speed
        self.on_event = on_event  # 回调(event_dict) 给 GUI/日志用
        self.use_mic = use_mic    # False=外部喂音频（模拟/测试用）
        self.history = history    # 可选：历史记录（不传=不记录）

        self.vad = SileroVad(threshold=vad_threshold)
        self.seg = VoiceSegmenter(
            self.vad, self._handle_segment,
            speech_threshold=vad_threshold, silence_ms=silence_ms,
            max_seg_s=max_seg_s, min_seg_s=min_seg_s, debug=debug,
        )

        self._audio_q = queue.Queue()
        self._running = False
        self._streams = []
        self._threads = []
        self._t_last_voice_end = None   # 句尾时刻（延迟测量用）
        self._processing_lock = threading.Lock()
        self._input_level = 0.0         # 最近采集块的 RMS（给 UI 音量条）
        self._actual_sr = MIC_SR        # 实际打开的输入流采样率
        self._mic_channels = 1
        self._mic_open_failed = False   # 输入流没打开（不阻塞启动）
        self._mic_open_error = ""

    # ---------- 生命周期 ----------
    def start(self):
        if self._running:
            return
        self.vad.load()
        self.vad.reset()
        self.seg.reset()
        self._running = True

        if self.use_mic:
            def audio_cb(indata, frames, t, status):
                if status:
                    pass
                import numpy as _np
                self._input_level = float(
                    _np.sqrt(_np.mean(indata ** 2)))
                a = indata
                # 非目标采样率（PortAudio 会自动重采样，但有些驱动不支持
                # 直接 16k——那时我们以设备默认采样率打开，这里手动降采样）
                if a.shape[0] and self._actual_sr != MIC_SR:
                    a = self._resample(a, self._actual_sr, MIC_SR)
                self._audio_q.put(a.copy())

            # 打开输入流：参数组合逐个回退，open+start 都成功才算通过。
            # 覆盖维度：采样率 × 声道数 × 采样格式。
            # Realtek 等阵列麦常见坑：
            #  - float32 被拒（只收 16bit PCM）→ 试 int16
            #  - WASAPI 对不支持的 sr 报 UNSUPPORTED_FORMAT / Invalid sample rate
            #    → 试设备默认采样率、常见采样率
            #  - 单声道降混被拒 → 试原生声道数
            # int16 路径：回调里转回 float32 喂给 VAD/STT。
            opened = False
            last_err = None

            def _make_cb(dtype):
                """按流的 dtype 包一层回调：统一转成 float32 单声道后入队。"""
                def cb(indata, frames, t, status):
                    import numpy as _np
                    self._input_level = float(
                        _np.sqrt(_np.mean(indata.astype(_np.float32) ** 2)))
                    a = indata
                    if dtype == "int16":
                        a = a.astype(_np.float32) / 32768.0
                    if a.shape[0] and self._actual_sr != MIC_SR:
                        a = self._resample(a, self._actual_sr, MIC_SR)
                    if a.ndim > 1 and a.shape[1] > 1:
                        a = a.mean(axis=1, keepdims=True)
                    self._audio_q.put(a.astype(_np.float32).copy())
                return cb

            # 设备维度：指定设备优先，其后是它的同名 Host API 变体
            # （WASAPI 共享模式最容易打开，见 _candidate_input_devices）
            for dev_idx in _candidate_input_devices(self.input_device):
                for sr in (MIC_SR, None, 48000, 44100):
                    for ch in (1, None):
                        for dt in ("float32", "int16"):
                            if opened:
                                break
                            try:
                                self._mic = sd.InputStream(
                                    device=dev_idx,
                                    samplerate=sr,          # None=设备默认
                                    channels=ch,
                                    blocksize=MIC_SR * BLOCK_MS // 1000,
                                    dtype=dt,
                                    callback=_make_cb(dt),
                                )
                                self._mic.start()  # start 失败也算失败
                                self._actual_sr = self._mic.samplerate
                                self._mic_channels = self._mic.channels
                                opened = True
                            except Exception as e:
                                last_err = e
                                try:
                                    if self._mic is not None:
                                        self._mic.close()
                                except Exception:
                                    pass
                                self._mic = None
            if not opened:
                # 用户要求：设备打不开时不阻塞启动，进入"无输入"模式继续运行。
                # 软件界面、翻译历史等一切功能照常，只是收不到声音；
                # 用户随时可以停止后换设备再启动。
                self._mic = None
                self._actual_sr = MIC_SR
                self._mic_channels = 1
                self._mic_open_failed = True
                self._mic_open_error = str(last_err)
            else:
                self._mic_open_failed = False
                self._mic_open_error = ""
        else:
            self._mic = None
            self._actual_sr = MIC_SR
            self._mic_channels = 1

        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        self._threads = [t]

    def stop(self):
        self._running = False
        if self._mic is not None:
            try:
                self._mic.stop()
                self._mic.close()
            except Exception:
                pass
        self._audio_q.put(None)  # 唤醒线程退出

    # ---------- 主循环 ----------
    def _loop(self):
        while self._running:
            try:
                item = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            mono = item.reshape(-1)
            self.seg.feed(mono)

    # ---------- 一句话处理 ----------
    def _handle_segment(self, seg_audio: np.ndarray):
        if not self._running:
            return
        t_voice_end = time.time()  # VAD 判定完静音的时刻
        ev = {
            "seg_dur": len(seg_audio) / MIC_SR,
            "voice_end_at": t_voice_end,
        }
        with self._processing_lock:
            audio_out, sr_out, pe = self.pipe.process_speech(
                seg_audio, MIC_SR, speed=self.speed
            )
            ev.update({
                "zh": pe.zh_text, "en": pe.en_text,
                "stages_ms": dict(pe.stages_ms), "total_ms": pe.total_ms,
                "ok": pe.ok, "error": pe.error,
            })
            if pe.ok:
                # 发送耗时也记入（播放启动前的准备）
                t0 = time.time()
                self.out.play_to_cable(audio_out, sr_out)
                ev["play_done_at"] = time.time()
                # 历史记录（只存文字：中文原文 + 英文译文 + 延迟）
                if self.history is not None:
                    try:
                        self.history.add(
                            pe.zh_text, pe.en_text,
                            delay_ms=ev.get("first_audio_delay_ms"),
                        )
                    except Exception:
                        pass  # 记录失败不影响主流程
        # 感知延迟：句尾(静音判定完) -> 整段英文播完
        if ev.get("ok"):
            first_audio_delay = None
            if ev.get("voice_end_at"):
                # play_to_cable 是阻塞到播完的；开始播放时刻 = 播完 - 音频时长
                first_audio_delay = (ev["play_done_at"]
                                     - ev["voice_end_at"]
                                     - len(audio_out) / sr_out)
            ev["first_audio_delay_ms"] = (
                first_audio_delay * 1000 if first_audio_delay else None
            )
        if self.on_event:
            try:
                self.on_event(ev)
            except Exception:
                pass

    @property
    def last_input_level(self) -> float:
        """最近采集块的音量 RMS（0~1），给 UI 音量条用。"""
        return self._input_level

    @staticmethod
    def _resample(a: "np.ndarray", from_sr: int, to_sr: int) -> "np.ndarray":
        """线性插值降/升采样（mono float32）。质量对 16k 语音识别足够。"""
        import numpy as _np
        if from_sr == to_sr or len(a) == 0:
            return a
        n_out = int(len(a) * to_sr / from_sr)
        x_out = _np.linspace(0, len(a) - 1, n_out)
        x_in = _np.arange(len(a))
        if a.ndim > 1:
            return _np.stack(
                [_np.interp(x_out, x_in, a[:, c]) for c in range(a.shape[1])],
                axis=1)
        return _np.interp(x_out, x_in, a).astype("float32")

    def set_speed(self, v: float):
        self.speed = max(0.5, min(2.0, v))

    def set_sensitivity(self, threshold: float, gain: float | None = None):
        """运行期调 VAD 灵敏度：threshold 越低越容易触发；
        gain None 时按 threshold 反算合理增益。"""
        threshold = max(0.1, min(0.8, threshold))
        self.vad.threshold = threshold
        self.seg.speech_threshold = threshold
        if gain is not None:
            self.vad.input_gain = max(1.0, min(12.0, gain))

    def set_volume(self, v: float):
        self.out.set_volume(v)

    def set_local_playback(self, on: bool):
        self.out.set_local_playback(on)
