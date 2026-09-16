# -*- coding: utf-8 -*-
"""tts 包：语音合成模块（可替换接口设计）。"""
from tts.base import TtsEngine, TtsError
from tts.tiny_tts import TinyTts

__all__ = ["TtsEngine", "TtsError", "TinyTts"]


def create_default_tts() -> TtsEngine:
    """工厂函数：当前默认 TTS 引擎。换引擎时只改这里。"""
    return TinyTts()
