# -*- coding: utf-8 -*-
"""TinyTTS 英文文本前端（无 PyTorch/nltk/g2p_en/transformers 版）。

官方 tiny_tts/text/english.py 依赖 g2p_en(nltk) 和 transformers AutoTokenizer，
违反本项目的"禁止 PyTorch"约束。这里用等价的轻量实现替代：
  - 词切分：CMU 字典 + 标点规则（翻译输出是规整英文，覆盖率高）
  - OOV 兜底：字母级拼写发音（拼写读出，保证不崩）
分词与音素映射逻辑与官方一致（cmudict.rep + cmudict_cache.pickle）。
"""
import os
import pickle
import re
import sys

_THIS = os.path.dirname(__file__)
# 打包后资源在 sys._MEIPASS；源码运行在项目根
_ROOT = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(_THIS, "..")))
_FRONT = os.path.join(_ROOT, "third_party", "tiny_tts_text")

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "tiny_tts_symbols", os.path.join(_FRONT, "symbols.py")
)
symbols_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(symbols_mod)

symbols = symbols_mod.symbols
_symbol_to_id = {s: i for i, s in enumerate(symbols)}
language_id_map = symbols_mod.language_id_map
language_tone_start_map = symbols_mod.language_tone_start_map

CMU_DICT_PATH = os.path.join(_FRONT, "cmudict.rep")
CACHE_PATH = os.path.join(_FRONT, "cmudict_cache.pickle")

# g2p_en 的 arpa 音素集（与官方 english.py 相同）
arpa = {
    "AH0", "S", "AH1", "EY2", "AE2", "EH0", "OW2", "UH0", "NG", "B",
    "G", "AY0", "M", "AA0", "F", "AO0", "ER2", "UH1", "IY1", "AH2",
    "DH", "IY0", "EY1", "IH0", "K", "N", "W", "IY2", "T", "AA1",
    "ER1", "EH2", "OY0", "UH2", "UW1", "Z", "AW2", "AW1", "V", "UW2",
    "AA2", "ER", "AW0", "UW0", "R", "OW1", "EH1", "ZH", "AE0", "IH2",
    "IH", "Y", "JH", "P", "AY1", "EY0", "OY2", "TH", "HH", "D",
    "ER0", "CH", "AO1", "AE1", "AO2", "OY1", "AY2", "IH1", "OW0", "L", "SH",
}

_rep_map = {
    "：": ",", "；": ",", "，": ",", "。": ".", "！": "!",
    "？": "?", "\n": ".", "·": ",", "、": ",", "...": "…", "v": "V",
}


def _get_dict():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)
    # 从 .rep 文本重建（首次运行生成）
    g2p_dict = {}
    with open(CMU_DICT_PATH, encoding="utf-8") as f:
        for line_index, line in enumerate(f, 1):
            if line_index >= 49:
                line = line.strip()
                parts = line.split("  ")
                if len(parts) != 2:
                    continue
                word = parts[0]
                syllables = parts[1].split(" - ")
                g2p_dict[word] = [s.split(" ") for s in syllables]
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(g2p_dict, f)
    return g2p_dict


eng_dict = _get_dict()

# ── 缩写/数字展开 ──────────────────────────────────────────
# 与官方 english_utils 相同的规则，内联实现避免 nltk
_ABBREV = [
    (re.compile(r"\b%s\." % p, re.I), r)
    for p, r in [
        ("mrs", "misess"), ("mr", "mister"), ("dr", "doctor"),
        ("st", "saint"), ("co", "company"), ("jr", "junior"),
        ("maj", "major"), ("gen", "general"), ("drs", "doctors"),
        ("rev", "reverend"), ("lt", "lieutenant"), ("hon", "honorable"),
        ("sgt", "sergeant"), ("capt", "captain"), ("esq", "esquire"),
        ("ltd", "limited"), ("col", "colonel"), ("ft", "fort"),
    ]
]

_UNITS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

_DIGITS = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
    19: "nineteen",
}
_TENS = {
    2: "twenty", 3: "thirty", 4: "forty", 5: "fifty",
    6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety",
}


def _num_to_words(n: int) -> str:
    if n < 20:
        return _DIGITS[n]
    if n < 100:
        t, u = divmod(n, 10)
        return _TENS[t] if u == 0 else _TENS[t] + " " + _DIGITS[u]
    if n < 1000:
        h, r = divmod(n, 100)
        return _DIGITS[h] + " hundred" + ("" if r == 0 else " and " + _num_to_words(r))
    return str(n)  # 大数（年份等）逐位读


def normalize_text(text: str) -> str:
    """小写 + 数字转读法 + 缩写展开。"""
    text = text.lower()
    for pat, rep in _ABBREV:
        text = pat.sub(rep, text)
    # 数字→英文读法（纯数字 token）
    def _digit_sub(m):
        s = m.group(0)
        try:
            return _num_to_words(int(s))
        except Exception:
            return " ".join(_UNITS[c] for c in s)
    text = re.sub(r"\d+", _digit_sub, text)
    return text


def _parse_phoneme(phn: str):
    tone = 0
    if re.search(r"\d$", phn):
        tone = int(phn[-1]) + 1
        phn = phn[:-1]
    return phn.lower(), tone


# 字母→类发音兜底（OOV 词，拼写读出）。给出近似 CMU 音素而非字母名，
# 避免引入 g2p_en。
_LETTER_ARPA = {
    "a": "AH", "b": "B", "c": "S", "d": "D", "e": "EH", "f": "F",
    "g": "G", "h": "HH", "i": "IY", "j": "JH", "k": "K", "l": "L",
    "m": "M", "n": "N", "o": "OW", "p": "P", "q": "K", "r": "R",
    "s": "S", "t": "T", "u": "UW", "v": "V", "w": "W", "x": "K S",
    "y": "Y", "z": "Z",
}


def _spell_word(w: str):
    """OOV 词：按字母拼写读出（带近似发音），保证永不崩。"""
    phones = []
    tones = []
    for ch in w:
        if ch in _LETTER_ARPA:
            for ph in _LETTER_ARPA[ch].split(" "):
                phones.append(ph.lower())
                tones.append(0)
        else:
            phones.append("UNK")
            tones.append(0)
    return phones, tones


def _map_ph(ph: str):
    if ph in _rep_map:
        ph = _rep_map[ph]
    if ph in symbols:
        return ph
    return "UNK"


def grapheme_to_phoneme(text: str, pad_start_end: bool = True):
    """文本 → (音素列表, 声调列表)。与官方接口一致。"""
    # 简易分词：按标点切开，词内字符归一词
    tokens = re.findall(r"[A-Za-z']+|[0-9]+|[.,!?;:…\"()-]", text)
    phones = []
    tones = []
    for tok in tokens:
        if not tok:
            continue
        if re.match(r"^[.,!?;:…\"()-]$", tok):
            ph = _map_ph(tok)
            if ph != "UNK":
                phones.append(ph)
                tones.append(0)
            continue
        up = tok.upper()
        if up in eng_dict:
            phns, tns = [], []
            for syll in eng_dict[up]:
                for phn in syll:
                    p, t = _parse_phoneme(phn)
                    phns.append(p)
                    tns.append(t)
            phones += phns
            tones += tns
        else:
            phns, tns = _spell_word(tok)
            phones += phns
            tones += tns
    phones = [_map_ph(p) for p in phones]
    if pad_start_end:
        phones = ["_"] + phones + ["_"]
        tones = [0] + tones + [0]
    return phones, tones, None


def phonemes_to_ids(cleaned_phones, tones, language: str = "EN"):
    unk_id = _symbol_to_id.get("UNK")
    phone_ids = [
        _symbol_to_id.get(p, unk_id) for p in cleaned_phones
    ]
    tone_start = language_tone_start_map[language]
    tone_ids = [t + tone_start for t in tones]
    lang_id = language_id_map[language]
    lang_ids = [lang_id] * len(phone_ids)
    return phone_ids, tone_ids, lang_ids
