# -*- coding: utf-8 -*-
"""opus-mt-zh-en 翻译引擎（默认实现）。

模型：Helsinki-NLP/opus-mt-zh-en 转换为 CTranslate2 格式 + int8 量化（81MB）
分词器：sentencepiece（source.spm / target.spm）
依赖：仅 ctranslate2 + sentencepiece，无需 PyTorch。

流水线（与 transformers MarianTokenizer 等价，已对照验证）：
  encode: SentencePiece pieces + '</s>' 结尾
  CT2:    translate_batch(pieces) -> hypotheses（token 片列表）
  decode: 目标 SentencePiece DecodePieces
"""
from pathlib import Path

import ctranslate2
import sentencepiece as spm

from translation.base import TranslatorEngine, TranslatorError
from paths import models_dir

# 模型目录（源码运行=项目根，打包后=_MEIPASS）
MODEL_DIR = models_dir() / "opus-mt-zh-en-ct2-int8"
TOK_DIR = models_dir() / "opus-mt-tokenizer"


class OpusMtTranslator(TranslatorEngine):
    def __init__(self, model_dir: Path = MODEL_DIR, tok_dir: Path = TOK_DIR):
        self.model_dir = Path(model_dir)
        self.tok_dir = Path(tok_dir)
        self._translator = None
        self._src_sp = None
        self._tgt_sp = None

    def load(self) -> None:
        if not self.model_dir.exists():
            raise TranslatorError(f"模型目录不存在：{self.model_dir}")
        spm_path = self.tok_dir / "source.spm"
        tgt_path = self.tok_dir / "target.spm"
        if not spm_path.exists() or not tgt_path.exists():
            raise TranslatorError(f"分词器文件缺失：{self.tok_dir}")
        try:
            self._translator = ctranslate2.Translator(
                str(self.model_dir), device="cpu",
                inter_threads=1, intra_threads=1,
            )
            self._src_sp = spm.SentencePieceProcessor()
            self._src_sp.Load(str(spm_path))
            self._tgt_sp = spm.SentencePieceProcessor()
            self._tgt_sp.Load(str(tgt_path))
        except Exception as e:
            raise TranslatorError(f"模型加载失败：{e}")
        # 预热：首次推理有冷启动开销（内核 JIT/内存映射）
        try:
            self.translate("预热")
        except Exception:
            pass

    def translate(self, text: str) -> str:
        if self._translator is None:
            raise TranslatorError("引擎未加载，请先调用 load()")
        text = (text or "").strip()
        if not text:
            return ""
        try:
            pieces = self._src_sp.EncodeAsPieces(text)
            pieces.append("</s>")  # Marian 要求句尾 </s>
            results = self._translator.translate_batch([pieces])
            out_pieces = results[0].hypotheses[0]
            # hypotheses 不含 </s>；直接用目标端分词器拼回文本
            return self._tgt_sp.DecodePieces(out_pieces).strip()
        except Exception as e:
            raise TranslatorError(f"翻译失败：{e}")

    def close(self) -> None:
        self._translator = None  # ct2 Translator 无显式 close，交给 GC
