# -*- coding: utf-8 -*-
"""TinyTTS 语音合成引擎（默认实现）。

模型：官方 4 件套 ONNX（text_encoder / duration_predictor / flow / decoder）
推理：与官方 tiny_tts/infer_onnx.py 完全一致的 pipeline，
     文本前端用本项目 tts/text_frontend.py（去 nltk/g2p_en/transformers 版）。
采样率：44100 Hz。
"""
import os
import threading
from pathlib import Path

import numpy as np

from tts.base import TtsEngine, TtsError
from tts import text_frontend as fe
from paths import models_dir

ONNX_DIR = models_dir() / "tinytts-onnx"
SAMPLING_RATE = 44100
SPK2ID = {"male": 0}  # config: spk2id {"MALE": 0}
ADD_BLANK = True


def _build_session(path: str, threads: int = 2):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.intra_op_num_threads = threads   # 限制线程：4核上多引擎并存时不互踩
    opts.inter_op_num_threads = 1
    return ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])


def _create_length_mask_np(lengths, max_len=None):
    if max_len is None:
        max_len = int(lengths.max())
    ids = np.arange(max_len, dtype=np.float32)
    return (ids[None, :] < lengths[:, None]).astype(np.float32)


def _compute_alignment_path_np(w_ceil, attn_mask):
    """Monotonic alignment（与官方 infer_onnx.py 一致）。"""
    _, _, T_x = w_ceil.shape
    T_y = attn_mask.shape[2]
    dur = w_ceil[:, 0, :]
    cum_dur = np.cumsum(dur, axis=1)
    cum_dur_prev = np.pad(cum_dur[:, :-1], ((0, 0), (1, 0)))
    frame_idx = np.arange(T_y, dtype=np.float32)[None, :, None]
    start = cum_dur_prev[:, None, :]
    end = cum_dur[:, None, :]
    attn = ((frame_idx >= start) & (frame_idx < end)).astype(np.float32)
    attn = attn[:, None, :, :]
    return attn * attn_mask


def _insert_blanks(ids, blank_id=0):
    """[a,b,c] -> [0,a,0,b,0,c,0]（官方 commons.insert_blanks）。"""
    out = [blank_id]
    for i in ids:
        out.append(i)
        out.append(blank_id)
    return out


class TinyTts(TtsEngine):
    def __init__(self, onnx_dir: Path = ONNX_DIR, speaker: str = "male"):
        self.onnx_dir = Path(onnx_dir)
        self.speaker = speaker
        self._sessions = None
        self._lock = threading.Lock()

    def load(self) -> None:
        needed = ["text_encoder.onnx", "duration_predictor.onnx",
                  "flow.onnx", "decoder.onnx"]
        missing = [f for f in needed if not (self.onnx_dir / f).exists()]
        if missing:
            raise TtsError(f"模型文件缺失：{missing}，目录：{self.onnx_dir}")
        try:
            self._sessions = {
                "enc": _build_session(str(self.onnx_dir / "text_encoder.onnx"), 1),
                "dp": _build_session(str(self.onnx_dir / "duration_predictor.onnx"), 1),
                "flow": _build_session(str(self.onnx_dir / "flow.onnx"), 2),
                "dec": _build_session(str(self.onnx_dir / "decoder.onnx"), 2),
            }
        except Exception as e:
            raise TtsError(f"模型加载失败：{e}")
        # 预热：跑一遍空合成，让 ORT 完成图优化/内存分配（首次推理慢数倍）
        try:
            self.synthesize("Warm up.", speed=1.0)
        except Exception:
            pass

    def synthesize(self, text: str, speed: float = 1.0) -> tuple:
        """合成语音。返回 (audio float32 mono, 44100)。"""
        if self._sessions is None:
            raise TtsError("引擎未加载，请先调用 load()")
        text = (text or "").strip()
        if not text:
            return np.zeros(0, dtype=np.float32), SAMPLING_RATE
        noise_scale = 0.667
        noise_scale_w = 0.8
        length_scale = 1.0 / max(0.1, speed)  # speed>1 语速快 => 时长缩

        with self._lock:
            try:
                return self._run_pipeline(text, noise_scale, noise_scale_w, length_scale)
            except Exception as e:
                raise TtsError(f"合成失败：{e}")

    def _run_pipeline(self, text, noise_scale, noise_scale_w, length_scale):
        # 1. 文本 → 音素 → id
        normalized = fe.normalize_text(text)
        phones, tones, _ = fe.grapheme_to_phoneme(normalized)
        phone_ids, tone_ids, lang_ids = fe.phonemes_to_ids(phones, tones, "EN")
        if ADD_BLANK:
            phone_ids = _insert_blanks(phone_ids, 0)
            tone_ids = _insert_blanks(tone_ids, 0)
            lang_ids = _insert_blanks(lang_ids, 0)

        T = len(phone_ids)
        x = np.array(phone_ids, dtype=np.int64)[None, :]
        x_len = np.array([T], dtype=np.int64)
        tone = np.array(tone_ids, dtype=np.int64)[None, :]
        lang = np.array(lang_ids, dtype=np.int64)[None, :]
        bert = np.zeros((1, 1024, T), dtype=np.float32)
        ja_bert = np.zeros((1, 768, T), dtype=np.float32)
        sid = np.array([SPK2ID.get(self.speaker, 0)], dtype=np.int64)

        # 2. encoder
        x_enc, m_p, logs_p, x_mask, g = self._sessions["enc"].run(
            None,
            {"phone_ids": x, "phone_lengths": x_len, "tone_ids": tone,
             "language_ids": lang, "bert": bert, "ja_bert": ja_bert,
             "speaker_id": sid},
        )

        # 3. duration predictor
        logw = self._sessions["dp"].run(
            None, {"x": x_enc, "x_mask": x_mask, "g": g}
        )[0]

        # 4. alignment
        w = np.exp(logw) * x_mask * length_scale
        w_ceil = np.ceil(w)
        y_len = max(1, int(w_ceil.sum()))
        y_lens = np.array([y_len], dtype=np.int64)
        y_mask = _create_length_mask_np(y_lens, y_len)[:, None, :]
        attn_mask = y_mask[:, :, :, None] * x_mask[:, :, None, :]
        attn = _compute_alignment_path_np(w_ceil, attn_mask)

        m_p_exp = np.matmul(attn[:, 0], m_p.transpose(0, 2, 1)).transpose(0, 2, 1)
        logs_p_exp = np.matmul(attn[:, 0], logs_p.transpose(0, 2, 1)).transpose(0, 2, 1)

        # 5. 采样 z_p
        z_p = m_p_exp + np.random.randn(*m_p_exp.shape).astype(np.float32) * \
            np.exp(logs_p_exp) * noise_scale

        # 6. flow (reverse)
        z = self._sessions["flow"].run(
            None, {"z_p": z_p, "y_mask": y_mask.astype(np.float32), "g": g}
        )[0]

        # 7. decoder
        z_masked = (z * y_mask).astype(np.float32)
        audio = self._sessions["dec"].run(None, {"z": z_masked, "g": g})[0]

        return audio[0, 0].astype(np.float32), SAMPLING_RATE

    def close(self) -> None:
        self._sessions = None
