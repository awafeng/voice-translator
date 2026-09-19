# -*- coding: utf-8 -*-
"""translation 包：机器翻译模块（可替换接口设计）。"""
from translation.base import TranslatorEngine, TranslatorError
from translation.opus_translator import OpusMtTranslator
from paths import models_dir

__all__ = ["TranslatorEngine", "TranslatorError", "OpusMtTranslator"]


def create_default_translator(direction: str = "zh2en") -> TranslatorEngine:
    """工厂函数：按翻译方向创建引擎。换引擎时只改这里。

    direction: "zh2en"（中译英，默认）| "en2zh"（英译中）
    """
    if direction == "zh2en":
        return OpusMtTranslator(
            model_dir=models_dir() / "opus-mt-zh-en-ct2-int8",
            tok_dir=models_dir() / "opus-mt-tokenizer")
    if direction == "en2zh":
        return OpusMtTranslator(
            model_dir=models_dir() / "opus-mt-en-zh-ct2-int8",
            tok_dir=models_dir() / "opus-mt-en-zh-tokenizer")
    raise ValueError(f"未知翻译方向：{direction}")
