# -*- coding: utf-8 -*-
"""翻译模块统一接口（可替换设计）。

所有机器翻译引擎都实现 TranslatorEngine 基类：
  - OpusMtTranslator（当前默认：opus-mt-zh-en CTranslate2 int8）
  - 将来可新增其他实现（如 NLLB、其他 CT2 模型等），不改上层调用逻辑
"""
from abc import ABC, abstractmethod


class TranslatorEngine(ABC):
    """中译英机器翻译引擎的统一接口。"""

    @abstractmethod
    def load(self) -> None:
        """加载模型（耗时操作，应在启动时调用一次）。"""

    @abstractmethod
    def translate(self, text: str) -> str:
        """把一句中文翻译成英文。"""

    @abstractmethod
    def close(self) -> None:
        """释放资源。"""


class TranslatorError(Exception):
    """翻译模块的统一异常。"""
