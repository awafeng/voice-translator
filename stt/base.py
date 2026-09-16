# -*- coding: utf-8 -*-
"""STT 模块统一接口（可替换设计）。

所有语音识别引擎都实现 SttEngine 基类：
  - MoonshineStt（当前默认，普通话流式）
  - 将来如需更换，只需新增一个子类，不改上层调用逻辑
"""
from abc import ABC, abstractmethod

import numpy as np


class SttEngine(ABC):
    """语音识别引擎的统一接口。约定：音频为 mono float32，幅度 [-1, 1]。"""

    @abstractmethod
    def load(self) -> None:
        """加载模型（耗时操作，应在启动时调用一次）。"""

    @abstractmethod
    def transcribe_file(self, audio: np.ndarray, sample_rate: int) -> str:
        """把一段完整音频转成文字。audio: mono float32 ndarray。"""

    @abstractmethod
    def close(self) -> None:
        """释放资源。"""

    # ---- 流式接口（可选实现，未实现的引擎返回 False）----
    def supports_streaming(self) -> bool:
        return False

    def start_stream(self) -> None:
        """开始一次流式识别会话。"""

    def feed_chunk(self, chunk: np.ndarray, sample_rate: int) -> None:
        """喂入一小段音频（流式模式用）。"""

    def finish_stream(self) -> str:
        """结束会话，返回这段音频的完整识别文字。"""
        raise NotImplementedError


class SttError(Exception):
    """STT 模块的统一异常。"""
