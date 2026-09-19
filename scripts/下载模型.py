# -*- coding: utf-8 -*-
"""一键下载所有模型（国内网络优化：默认走 hf-mirror.com 镜像）。

下载内容（共约 146MB）：
  1. moonshine-zh        语音识别（流式中文小模型，31MB）——用 moonshine_voice
                          官方下载器（自动校验完整性），缓存后复制到 models/
  2. opus-mt-zh-en int8  翻译模型（CTranslate2 int8，78MB）——直接下转换好的
                          离线包（见 REPO_RELEASE_URL，也可自行转换，
                          见 scripts/convert_opus_mt.py）
  3. TinyTTS 4 件套      英文语音合成（32MB）
  4. silero_vad.onnx     语音活动检测（2.2MB）
  5. cmudict.rep         CMU 发音词典（TinyTTS 文本前端用）

用法：双击 scripts/下载模型.bat，或
  venv\\Scripts\\python.exe scripts\\下载模型.py
"""
import os
import shutil
import sys
import urllib.request
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
MODELS = PROJ / "models"
THIRD = PROJ / "third_party" / "tiny_tts_text"

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# 国内直连 HF 被墙，走 hf-mirror 镜像；海外用户可设 HF_ENDPOINT=https://huggingface.co
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")

# opus-mt-zh-en 的 CTranslate2 int8 离线包（已转换好，免去本地转换）。
# 放在 GitHub Release；若不可达可手动下载后解压到 models/opus-mt-zh-en-ct2-int8/
REPO_RELEASE_URL = ""  # TODO: 开源后填上 Release 直链；为空时用 HF 原始模型+提示转换


def download(url: str, dest: Path, desc: str):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  ✓ 已存在，跳过: {dest.name}")
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  ↓ 下载 {desc}: {url}")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length", 0)) or None
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    print(f"\r    {pct:3d}%  {done/1e6:.1f}/{total/1e6:.1f} MB",
                          end="", flush=True)
        print()
        tmp.rename(dest)
    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(f"下载失败 {desc}: {e}") from e


def step(msg):
    print(f"\n== {msg} ==")


def main():
    direction = "en2zh" if "--en2zh" in sys.argv else "zh2en"
    print("=" * 60)
    print(f"VoiceTranslator 模型一键下载（方向: {direction}）")
    print(f"镜像: {HF_ENDPOINT}")
    print("=" * 60)

    # ── 1. Moonshine 语音识别模型（官方下载器：CRC 校验 + 断点）──
    if direction == "zh2en":
        step("1/4 moonshine-zh 语音识别模型")
        lang, stt_dst = "zh", MODELS / "moonshine-zh"
    else:
        step("1/4 moonshine-en-tiny 语音识别模型（英文）")
        lang, stt_dst = "en", MODELS / "moonshine-en-tiny"
    try:
        from moonshine_voice.download import get_model_for_language
        from moonshine_voice.moonshine_api import ModelArch
        cached_path, arch = get_model_for_language(
            lang, wanted_model_arch=ModelArch.TINY_STREAMING,
            cache_root=MODELS / "_moonshine_cache",
            on_progress=lambda f, m: print(
                f"\r    {f*100:3.0f}%  {m}", end="", flush=True))
        print()
        if Path(cached_path).resolve() != stt_dst.resolve():
            if stt_dst.exists():
                shutil.rmtree(stt_dst)
            shutil.copytree(cached_path, stt_dst)
        shutil.rmtree(MODELS / "_moonshine_cache", ignore_errors=True)
        print(f"  ✓ 就绪: {stt_dst}")
    except Exception as e:
        print(f"\n  ✗ Moonshine {lang} 下载失败: {e}")
        print("    （该模型也可手动下载：见 README「模型下载」一节）")
        raise

    # ── 2. opus-mt 翻译模型（CT2 int8）──
    if direction == "zh2en":
        mt_repo, mt_dst = "opus-mt-zh-en", MODELS / "opus-mt-zh-en-ct2-int8"
    else:
        mt_repo, mt_dst = "opus-mt-en-zh", MODELS / "opus-mt-en-zh-ct2-int8"
    step(f"2/4 {mt_repo} 翻译模型（CTranslate2 int8）")
    if REPO_RELEASE_URL:
        import tempfile, zipfile
        z = Path(tempfile.gettempdir()) / f"{mt_repo}-ct2-int8.zip"
        download(REPO_RELEASE_URL, z, "opus-mt int8 离线包")
        with zipfile.ZipFile(z) as f:
            f.extractall(MODELS)
        print(f"  ✓ 解压就绪: {mt_dst}")
    else:
        # 从 HF 镜像下原始模型，提示用 convert_opus_mt.py 自行转换
        base = f"{HF_ENDPOINT}/Helsinki-NLP/{mt_repo}/resolve/main"
        raw = PROJ / "test_output" / "_opus_mt_raw"
        download(f"{base}/config.json", raw / "config.json", "config.json")
        download(f"{base}/pytorch_model.bin", raw / "pytorch_model.bin",
                 "pytorch_model.bin (~310MB)")
        download(f"{base}/source.spm", raw / "source.spm", "source.spm")
        download(f"{base}/target.spm", raw / "target.spm", "target.spm")
        download(f"{base}/vocab.json", raw / "vocab.json", "vocab.json")
        print("  ✓ 原始模型已下载，正在转换 int8（需临时安装 ctranslate2+transformers+torch）……")
        _convert_opus(raw, mt_dst)
        # en→zh 的分词器用模型自带的 spm（与 zh→en 的不同）
        tok_dst = (MODELS / "opus-mt-tokenizer" if direction == "zh2en"
                   else MODELS / "opus-mt-en-zh-tokenizer")
        tok_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy(raw / "source.spm", tok_dst / "source.spm")
        shutil.copy(raw / "target.spm", tok_dst / "target.spm")
        print(f"  ✓ 转换就绪: {mt_dst}")

    # ── 3. TTS ──
    if direction == "zh2en":
        step("3/4 TinyTTS 语音合成模型（英文）")
        base = f"{HF_ENDPOINT}/moonshineai/tiny-tts/resolve/main"
        for f in ("text_encoder.onnx", "duration_predictor.onnx",
                  "flow.onnx", "decoder.onnx"):
            download(f"{base}/{f}", MODELS / "tinytts-onnx" / f, f)
    else:
        step("3/4 Piper 中文合成模型（chaowen）+ g2pW 前端")
        vbase = (f"{HF_ENDPOINT}/rhasspy/piper-voices/resolve/main"
                 "/zh/zh_CN/chaowen/medium")
        download(f"{vbase}/zh_CN-chaowen-medium.onnx",
                 MODELS / "piper-zh" / "zh_CN-chaowen-medium.onnx",
                 "chaowen 声音模型 (61MB)")
        download(f"{vbase}/zh_CN-chaowen-medium.onnx.json",
                 MODELS / "piper-zh" / "zh_CN-chaowen-medium.onnx.json",
                 "声音配置")
        gbase = ("https://raw.githubusercontent.com/GitYCC/g2pW/master/g2pw")
        g2pw_dir = MODELS / "piper-zh" / "g2pw"
        download(f"{gbase}/POLYPHONIC_CHARS.txt", g2pw_dir / "POLYPHONIC_CHARS.txt",
                 "多音字表")
        download(f"{gbase}/MONOPHONIC_CHARS.txt", g2pw_dir / "MONOPHONIC_CHARS.txt",
                 "单音字表")
        download(f"{gbase}/bert-base-chinese_s2t_dict.txt",
                 g2pw_dir / "bert-base-chinese_s2t_dict.txt", "简繁对照表")
        download(f"{gbase}/bopomofo_to_pinyin_wo_tune_dict.json",
                 g2pw_dir / "bopomofo_to_pinyin_wo_tune_dict.json", "注音映射")
        download(f"{gbase}/char_bopomofo_dict.json",
                 g2pw_dir / "char_bopomofo_dict.json", "字注音表")
        download(f"{gbase}/config.py", g2pw_dir / "config.py", "g2pw 配置")
        # g2pw.onnx 在 piper-checkpoints 的 tar 包里（113MB）
        import tarfile
        tgz = MODELS / "piper-zh" / "_g2pw.tar.gz"
        download("https://hf-mirror.com/datasets/rhasspy/piper-checkpoints"
                 "/resolve/main/zh/zh_CN/_resources/g2pw.tar.gz",
                 tgz, "g2pw.onnx 模型包 (113MB)")
        with tarfile.open(tgz) as f:
            f.extractall(g2pw_dir)
        tgz.unlink()
        # g2pw 的 Bert 分词器（本地离线用，禁止运行时联网）
        bbase = f"{HF_ENDPOINT}/bert-base-chinese/resolve/main"
        for f in ("vocab.txt", "config.json", "tokenizer_config.json",
                  "tokenizer.json"):
            download(f"{bbase}/{f}",
                     MODELS / "piper-zh" / "bert-base-chinese" / f, f)

    # ── 4. Silero VAD + cmudict ──
    step("4/4 Silero VAD + CMU 词典")
    download("https://github.com/snakers4/silero-vad/raw/master"
             "/src/silero_vad/data/silero_vad.onnx",
             MODELS / "silero-vad" / "silero_vad.onnx", "silero_vad.onnx")
    download("https://raw.githubusercontent.com/cmusphinx/cmudict/master"
             "/cmudict.dict",
             THIRD / "cmudict.rep", "cmudict.rep")

    print("\n" + "=" * 60)
    print("全部模型就绪！双击 scripts/8-图形界面.bat 即可使用。")
    print("=" * 60)


def _convert_opus(raw_dir: Path, dst: Path):
    """临时环境转换 opus-mt → CT2 int8（优先复用 scripts/convert_opus_mt.py）。"""
    import subprocess
    code = f"""
import sys
from pathlib import Path
sys.path.insert(0, r"{PROJ / 'scripts'}")
import convert_opus_mt
"""
    # convert_opus_mt.py 的 DL 常量是 .convert_env/dl —— 把 raw 挪过去最省事
    dl = PROJ / ".convert_env" / "dl"
    dl.parent.mkdir(parents=True, exist_ok=True)
    if dl.exists():
        shutil.rmtree(dl)
    shutil.move(str(raw_dir), str(dl))
    extra = ["--en2zh"] if "en-zh" in str(dst) else []
    r = subprocess.run([sys.executable,
                        str(PROJ / "scripts" / "convert_opus_mt.py")] + extra,
                       cwd=str(PROJ))
    if r.returncode != 0 or not dst.exists():
        raise RuntimeError("opus-mt 转换失败，可手动运行 scripts/convert_opus_mt.py")


if __name__ == "__main__":
    main()
