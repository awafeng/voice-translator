# -*- coding: utf-8 -*-
"""VAD 模块统一接口 + Silero VAD 实现（ONNX）。

Silero VAD v5 接口（onnx-community 导出）：
  input:  (N, 512@16k) float —— 一块音频（16k 采样率时 512 采样 = 32ms）
  state:  (2, 1, 128) float —— 循环状态
  sr:     标量 int64 —— 采样率（只支持 8000 / 16000）
  output: (N, 1) 语音概率；stateN: 新状态
"""
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np

from paths import models_dir

MODEL_PATH = models_dir() / "silero-vad" / "silero_vad.onnx"


class VadEngine(ABC):
    """语音活动检测引擎统一接口。"""

    @abstractmethod
    def load(self) -> None:
        ...

    @abstractmethod
    def reset(self) -> None:
        """开始一段新的检测会话（清空内部状态）。"""

    @abstractmethod
    def is_speech(self, chunk: np.ndarray) -> float:
        """喂一块 16kHz mono 音频（512 采样整倍数），返回该块的语音概率。"""


class VadError(Exception):
    pass


class SileroVad(VadEngine):
    FRAME = 512  # 16k 时 32ms/帧

    def __init__(self, model_path: Path = MODEL_PATH, threshold: float = 0.35,
                 input_gain: float = 6.0):
        """
        threshold:  语音判定门槛（默认 0.35：小声说话也能触发；
                    环境吵/误触发多时调回 0.5）
        input_gain: 送入 VAD 前的软件增益。小音量麦克风先把信号放大，
                    Silero 对增益后的人声判定很鲁棒。只影响 VAD 判定，
                    不改变送入识别引擎的原始音频。
        """
        self.model_path = Path(model_path)
        self.threshold = threshold
        self.input_gain = input_gain
        self._sess = None
        self._state = None

    def load(self) -> None:
        if not self.model_path.exists():
            raise VadError(f"VAD 模型缺失：{self.model_path}")
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 2
            self._sess = ort.InferenceSession(
                str(self.model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
        except Exception as e:
            raise VadError(f"VAD 模型加载失败：{e}")
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def is_speech(self, chunk: np.ndarray) -> float:
        """返回这块音频的语音概率（0~1）。chunk 必须是 512 的整倍数。"""
        if self._sess is None:
            raise VadError("VAD 未加载")
        a = np.asarray(chunk, dtype=np.float32).reshape(-1)
        # 软件增益：小声说话先放大再判定（提高小音量下的触发灵敏度）
        if self.input_gain != 1.0:
            a = np.clip(a * self.input_gain, -1.0, 1.0)
        n_frames = len(a) // self.FRAME
        probs = []
        state = self._state
        sr = np.array(16000, dtype=np.int64)
        for i in range(n_frames):
            frame = a[i * self.FRAME:(i + 1) * self.FRAME][None, :]
            out, state = self._sess.run(
                None, {"input": frame, "state": state, "sr": sr}
            )
            probs.append(float(out[0, 0]))
        self._state = state
        # 多帧取最大概率（保守：只要有一帧像语音就算）
        return max(probs) if probs else 0.0


class VoiceSegmenter:
    """VAD + 分块策略：把连续麦克风流切成"一句一句"。

    策略（可配置，不写死）：
      - VAD 概率 >= speech_threshold 判定为"说话中"
      - 说话开始前积累少量 pre_roll 音频（避免吃掉句首）
      - 说话后连续 silence_ms 毫秒静音 => 判定句子结束，触发 on_segment
      - max_seg_s: 单句最大时长兜底（说到上限强制切）
      - min_seg_s: 少于这个时长且已静音 => 丢弃（滤掉"嗯""咳嗽"）
    """

    def __init__(self, vad: VadEngine, on_segment,
                 speech_threshold: float = 0.5,
                 silence_ms: int = 600,
                 pre_roll_ms: int = 200,
                 max_seg_s: float = 12.0,
                 min_seg_s: float = 0.4,
                 debug: bool = False):
        self.vad = vad
        self.on_segment = on_segment        # callback(np.ndarray audio16k)
        self.speech_threshold = speech_threshold
        self.silence_ms = silence_ms
        self.pre_roll_ms = pre_roll_ms
        self.max_seg_s = max_seg_s
        self.min_seg_s = min_seg_s
        self.debug = debug

        self._buf = []            # 当前句子的音频（含 pre-roll）
        self._pre = []            # 说完一句后的静音尾巴缓冲
        self._in_speech = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._frame_ms = 32       # 512@16k
        self._pending_tail = []   # 结尾静音缓存（等待可能的新句首）

    def reset(self):
        self._buf = []
        self._pending_tail = []
        self._in_speech = False
        self._silence_frames = 0
        self._speech_frames = 0
        self.vad.reset()

    def _dbg(self, *a):
        if self.debug:
            print(*a)

    def feed(self, chunk: np.ndarray) -> None:
        """喂入 16kHz mono 块（内部按 512 切帧，余数留到下块）。"""
        # 拼上上块余数
        if self._pending_tail:
            chunk = np.concatenate([np.concatenate(self._pending_tail), np.asarray(chunk)])
            self._pending_tail = []
        a = np.asarray(chunk, dtype=np.float32).reshape(-1)
        n_frames = len(a) // SileroVad.FRAME
        if n_frames == 0:
            self._pending_tail = [a]
            return
        whole = a[: n_frames * SileroVad.FRAME]
        rest = a[n_frames * SileroVad.FRAME:]
        if len(rest):
            self._pending_tail = [rest]

        for i in range(n_frames):
            frame = whole[i * SileroVad.FRAME:(i + 1) * SileroVad.FRAME]
            p = self.vad.is_speech(frame)  # 单帧
            self._process_frame(frame, p)

    def _process_frame(self, frame, prob):
        fms = self._frame_ms
        speech = prob >= self.speech_threshold

        if not self._in_speech:
            # 等待句首：保留最近 pre_roll_ms 的音频
            self._pre.append(frame)
            if len(self._pre) > int(self.pre_roll_ms / fms):
                self._pre.pop(0)
            if speech:
                self._in_speech = True
                self._buf = list(self._pre) + [frame]
                self._speech_frames = 1
                self._silence_frames = 0
                self._dbg(f"[VAD] 句首 (p={prob:.2f})")
        else:
            self._buf.append(frame)
            self._speech_frames += 1
            if speech:
                self._silence_frames = 0
            else:
                self._silence_frames += 1
                # 句尾判定：连续静音够长
                if self._silence_frames * fms >= self.silence_ms:
                    self._emit()
                elif self._speech_frames * fms >= self.max_seg_s * 1000:
                    self._emit()  # 时长兜底强制切

    def _emit(self):
        seg = np.concatenate(self._buf)
        dur = len(seg) / 16000
        self._in_speech = False
        self._silence_frames = 0
        self._buf = []
        if dur < self.min_seg_s:
            self._dbg(f"[VAD] 丢弃过短段 {dur:.2f}s")
            self._pre = []
            return
        self._dbg(f"[VAD] 句子完成 {dur:.2f}s -> 送翻译")
        # pre 缓冲清空，开始积累下一句的 pre-roll
        self._pre = []
        self.on_segment(seg)

    def flush(self):
        """停止时强制把缓住的句子发出。"""
        if self._in_speech and self._buf:
            self._emit()
