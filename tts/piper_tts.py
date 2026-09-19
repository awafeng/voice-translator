# -*- coding: utf-8 -*-
"""Piper 中文语音合成引擎（英译中版本用）。

模型：piper zh_CN-chaowen-medium ONNX（22.05kHz，数据集 CC0）
前端：拼音音素化 = g2pW ONNX（免 torch，移植自 OHF-Voice/piper1-gpl，
     Apache-2.0，见 third_party/piper_zh/）+ unicode-rbnf 数字转中文
推理：onnxruntime（与全项目共用同一份 ORT——piper1-gpl 是纯 Python 包
     无自带原生 DLL，不会复现"双 ORT 堆损坏"问题）

音频参数（来自 onnx.json）：noise_scale 0.667 / noise_w 0.8 /
length_scale 1.0（speed 越大读越快 → length_scale=1/speed）。
"""
import os
import sys

# 中文前端（g2pw 的 BertTokenizer）加载必须全程离线：本地文件已齐
# （models/piper-zh/bert-base-chinese/），联网重试会把加载拖到几分钟
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
from pathlib import Path

import numpy as np

from tts.base import TtsEngine, TtsError
from paths import models_dir

VOICE_PATH = models_dir() / "piper-zh" / "zh_CN-chaowen-medium.onnx"
VOICE_CONFIG = models_dir() / "piper-zh" / "zh_CN-chaowen-medium.onnx.json"
G2PW_DIR = models_dir() / "piper-zh" / "g2pw"
BERT_TOK_DIR = models_dir() / "piper-zh" / "bert-base-chinese"


def _ort_session(path: Path, threads: int = 2):
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), sess_options=opts,
                                providers=["CPUExecutionProvider"])


class PiperTts(TtsEngine):
    def __init__(self, voice_path: Path = VOICE_PATH):
        self.voice_path = Path(voice_path)
        self._session = None
        self._phonemizer = None
        self._config = None
        self._lock = __import__("threading").Lock()

    def load(self) -> None:
        if not self.voice_path.exists():
            raise TtsError(f"模型文件缺失：{self.voice_path}")
        try:
            import json
            self._config = json.loads(
                Path(str(self.voice_path) + ".json").read_text(encoding="utf-8"))
            self._session = _ort_session(self.voice_path, threads=2)
        except Exception as e:
            raise TtsError(f"模型加载失败：{e}")
        # 中文前端（g2pw onnx + bert 分词器，全部本地离线）
        try:
            _vendor = models_dir().parent / "third_party" / "piper_zh"
            # 打包后 third_party 在 _MEIPASS 下
            from paths import base_dir
            vendor = base_dir() / "third_party" / "piper_zh"
            if not vendor.exists():
                vendor = _vendor
            sys.path.insert(0, str(vendor.parent))
            from piper_zh.phonemize_chinese import ChinesePhonemizer
            from transformers import BertTokenizer
            self._phonemizer = ChinesePhonemizer(model_dir=G2PW_DIR)
            self._phonemizer.g2p.tokenizer = BertTokenizer.from_pretrained(
                str(BERT_TOK_DIR))
        except Exception as e:
            raise TtsError(f"中文前端加载失败：{e}")
        # 预热
        try:
            self.synthesize("预热。")
        except Exception:
            pass

    def synthesize(self, text: str, speed: float = 1.0) -> tuple:
        if self._session is None or self._phonemizer is None:
            raise TtsError("引擎未加载，请先调用 load()")
        text = (text or "").strip()
        if not text:
            return np.zeros(0, dtype=np.float32), self._sample_rate()
        length_scale = 1.0 / max(0.1, speed)
        with self._lock:
            try:
                return self._run(text, length_scale)
            except TtsError:
                raise
            except Exception as e:
                raise TtsError(f"合成失败：{e}")

    def _sample_rate(self) -> int:
        return int(self._config.get("audio", {}).get("sample_rate", 22050))

    def _run(self, text: str, length_scale: float) -> tuple:
        from piper_zh.phonemize_chinese import phonemes_to_ids

        # 1. 文本 → 拼音音素 → id（piper 中文按"组"插 padding）
        phonemes = self._phonemizer.phonemize(text)[0]
        ids = phonemes_to_ids(phonemes)
        if len(ids) <= 2:  # 只剩 BOS/EOS = 没内容
            return np.zeros(0, dtype=np.float32), self._sample_rate()

        x = np.array(ids, dtype=np.int64)[None, :]
        x_length = np.array([x.shape[1]], dtype=np.int64)
        sid = None
        if self._config.get("num_speakers", 1) > 1:
            sid = np.array([0], dtype=np.int64)

        # 2. 推理（piper 声音模型是单图端到端：输入音素 id → 输出音频）
        noise_scale = float(self._config["inference"]["noise_scale"])
        noise_w = float(self._config["inference"]["noise_w"])
        feed = {"input": x, "input_lengths": x_length,
                "scales": np.array([noise_scale, length_scale, noise_w],
                                   dtype=np.float32)}
        if sid is not None:
            feed["sid"] = sid
        audio = self._session.run(None, feed)[0]
        return audio.squeeze().astype(np.float32), self._sample_rate()

    def close(self) -> None:
        self._session = None
        self._phonemizer = None
