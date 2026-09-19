# -*- coding: utf-8 -*-
"""tts 包：语音合成模块（可替换接口设计）。"""
from tts.base import TtsEngine, TtsError
from tts.tiny_tts import TinyTts
from tts.piper_tts import PiperTts

__all__ = ["TtsEngine", "TtsError", "TinyTts", "PiperTts"]


def create_default_tts(direction: str = "zh2en") -> TtsEngine:
    """工厂函数：按翻译方向创建 TTS（合成"发给对方的话"）。

    direction: "zh2en"→英文合成(TinyTTS) | "en2zh"→中文合成(Piper)
    """
    if direction == "zh2en":
        return TinyTts()
    if direction == "en2zh":
        return PiperTts()
    raise ValueError(f"未知翻译方向：{direction}")
