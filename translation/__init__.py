# -*- coding: utf-8 -*-
"""translation 包：机器翻译模块（可替换接口设计）。"""
from translation.base import TranslatorEngine, TranslatorError
from translation.opus_translator import OpusMtTranslator

__all__ = ["TranslatorEngine", "TranslatorError", "OpusMtTranslator"]


def create_default_translator() -> TranslatorEngine:
    """工厂函数：当前默认翻译引擎。换引擎时只改这里。"""
    return OpusMtTranslator()
