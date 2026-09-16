# -*- coding: utf-8 -*-
"""stt 包：语音识别模块（可替换接口设计）。"""
from stt.base import SttEngine, SttError
from stt.moonshine_stt import MoonshineStt

__all__ = ["SttEngine", "SttError", "MoonshineStt"]


def create_default_stt() -> SttEngine:
    """工厂函数：当前默认 STT 引擎。换引擎时只改这里。"""
    return MoonshineStt()
