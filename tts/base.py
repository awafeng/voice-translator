# -*- coding: utf-8 -*-
"""TTS 模块统一接口（可替换设计）。

所有语音合成引擎都实现 TtsEngine 基类：
  - TinyTts（当前默认：TinyTTS ONNX 四件套）
  - 将来可新增 Piper / KittenTTS 等实现，不改上层调用逻辑
"""
from abc import ABC, abstractmethod

import numpy as np


class TtsEngine(ABC):
    """英文文本→语音引擎的统一接口。"""

    @abstractmethod
    def load(self) -> None:
        """加载模型。"""

    @abstractmethod
    def synthesize(self, text: str, speed: float = 1.0) -> tuple:
        """合成语音。返回 (audio: float32 mono [-1,1], sample_rate: int)。"""

    @abstractmethod
    def close(self) -> None:
        """释放资源。"""


class TtsError(Exception):
    """TTS 模块的统一异常。"""
