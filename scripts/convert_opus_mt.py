# -*- coding: utf-8 -*-
"""阶段3 工具：把 opus-mt-zh-en 转换为 CTranslate2 int8 格式。
运行环境：.convert_env（一次性转换环境，转换完删除）。
"""
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

DL = Path(__file__).resolve().parent.parent / ".convert_env" / "dl"
# 输出目录按方向：--en2zh 转英译中模型，默认转中译英
if "--en2zh" in sys.argv:
    OUT = (Path(__file__).resolve().parent.parent / "models"
           / "opus-mt-en-zh-ct2-int8")
else:
    OUT = (Path(__file__).resolve().parent.parent / "models"
           / "opus-mt-zh-en-ct2-int8")

import ctranslate2
import transformers
from transformers import MarianMTModel, MarianTokenizer

# ── 兼容补丁 ─────────────────────────────────────────────
# ct2 4.8.2 转换器会把 dtype=None 传给 transformers 4.46 的 from_pretrained，
# 而 MarianMTModel.__init__ 不认识该参数。把 None 过滤掉即可。
_orig_load_model = ctranslate2.converters.TransformersConverter.load_model


def _patched_load_model(self, model_class, model_name_or_path, **kwargs):
    kwargs.pop("dtype", None)
    return _orig_load_model(self, model_class, model_name_or_path, **kwargs)


ctranslate2.converters.TransformersConverter.load_model = _patched_load_model
# ── 补丁结束 ─────────────────────────────────────────────

print("加载原始模型（PyTorch 格式）……")
model = MarianMTModel.from_pretrained(DL, local_files_only=True)
tokenizer = MarianTokenizer.from_pretrained(DL, local_files_only=True)
print(f"transformers {transformers.__version__} 加载完成")

OUT.mkdir(parents=True, exist_ok=True)
print(f"转换为 CTranslate2 格式并做 int8 量化，输出到 {OUT} ……")
ctranslate2.converters.TransformersConverter(
    str(DL),
).convert(
    output_dir=str(OUT),
    quantization="int8",
    force=True,
)
print("转换完成。")

import os
total = 0
for f in sorted(OUT.rglob("*")):
    if f.is_file():
        total += f.stat().st_size
        print(f"  {f.name}: {f.stat().st_size/1e6:.1f} MB")
print(f"模型总体积：{total/1e6:.0f} MB（原 pytorch_model.bin 是 312MB）")

# 快速验证：用转换后的模型翻译一句
print()
print("转换后模型冒烟测试……")
translator = ctranslate2.Translator(str(OUT), device="cpu", inter_threads=1)
tok = MarianTokenizer.from_pretrained(DL, local_files_only=True)
src = "今天天气真好，我们去公园散步吧。"
tokens = tok.convert_ids_to_tokens(tok.encode(src))
results = translator.translate_batch([tokens])
out_tokens = results[0].hypotheses[0]
print(f"输入：{src}")
print(f"输出：{tok.decode(tok.convert_tokens_to_ids(out_tokens))}")
