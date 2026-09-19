# -*- coding: utf-8 -*-
"""stt 包：语音识别模块（可替换接口设计）。"""
from stt.base import SttEngine, SttError
from stt.moonshine_stt import MoonshineStt
from paths import models_dir

__all__ = ["SttEngine", "SttError", "MoonshineStt"]


def create_default_stt(direction: str = "zh2en") -> SttEngine:
    """工厂函数：按翻译方向创建 STT（识别"你说的话"）。

    direction: "zh2en"→中文识别 | "en2zh"→英文识别
    """
    if direction == "zh2en":
        return MoonshineStt(model_dir=models_dir() / "moonshine-zh")
    if direction == "en2zh":
        return MoonshineStt(model_dir=models_dir() / "moonshine-en-tiny")
    raise ValueError(f"未知翻译方向：{direction}")
