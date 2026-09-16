# -*- coding: utf-8 -*-
"""流水线编排层：STT -> 翻译 -> TTS -> 输出。

这一层只负责"把三个模块串起来"，不含任何模型逻辑。
模块通过构造函数注入（都实现各自的基类接口），因此三段都可替换。
"""
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np


@dataclass
class PipelineEvent:
    """一次完整翻译的事件记录（调试模式打印 & 历史记录用）。"""
    zh_text: str = ""
    en_text: str = ""
    stages_ms: dict = field(default_factory=dict)  # 各阶段耗时
    total_ms: float = 0.0
    ok: bool = False
    error: str = ""


class TranslationPipeline:
    def __init__(self, stt, translator, tts, debug: bool = False,
                 debug_print: Optional[Callable] = None):
        """
        stt: SttEngine；translator: TranslatorEngine；tts: TtsEngine
        debug: 打开时通过 debug_print 回调输出中间文字
        """
        self.stt = stt
        self.translator = translator
        self.tts = tts
        self.debug = debug
        self.debug_print = debug_print or print

    def load_all(self):
        t0 = time.time()
        self.stt.load()
        self.translator.load()
        self.tts.load()
        return time.time() - t0

    def process_speech(self, audio: np.ndarray, sample_rate: int,
                       speed: float = 1.0) -> tuple:
        """一段完整中文语音 -> (英文音频, 采样率, PipelineEvent)。

        audio: mono float32 [-1,1]。
        """
        ev = PipelineEvent()
        t_start = time.time()

        # 1. 识别
        t0 = time.time()
        zh = self.stt.transcribe_file(audio, sample_rate)
        ev.stages_ms["识别STT"] = (time.time() - t0) * 1000
        ev.zh_text = zh
        self._dbg(f"[STT] {zh!r}")
        if not zh.strip():
            ev.error = "未识别到语音内容"
            return None, None, ev

        # 2. 翻译
        t0 = time.time()
        en = self.translator.translate(zh)
        ev.stages_ms["翻译MT"] = (time.time() - t0) * 1000
        ev.en_text = en
        self._dbg(f"[MT ] {en!r}")
        if not en.strip():
            ev.error = "翻译结果为空"
            return None, None, ev

        # 3. 合成
        t0 = time.time()
        audio_out, sr = self.tts.synthesize(en, speed=speed)
        ev.stages_ms["合成TTS"] = (time.time() - t0) * 1000
        self._dbg(f"[TTS] {len(audio_out)/sr:.2f}s audio @ {sr}Hz")

        ev.total_ms = (time.time() - t_start) * 1000
        ev.ok = True
        return audio_out, sr, ev

    def _dbg(self, msg: str):
        if self.debug:
            self.debug_print(msg)

    def close(self):
        for m in (self.stt, self.translator, self.tts):
            try:
                m.close()
            except Exception:
                pass
