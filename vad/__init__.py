# -*- coding: utf-8 -*-
"""vad 包：语音活动检测（可替换接口设计）。"""
from vad.silero_vad import VadEngine, VadError, SileroVad, VoiceSegmenter

__all__ = ["VadEngine", "VadError", "SileroVad", "VoiceSegmenter"]


def create_default_vad() -> VadEngine:
    return SileroVad()
