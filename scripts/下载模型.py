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
    print("=" * 60)
    print("VoiceTranslator 模型一键下载")
    print(f"镜像: {HF_ENDPOINT}")
    print("=" * 60)

    # ── 1. moonshine-zh（官方下载器：自带 CRC 校验 + 断点逻辑）──
    step("1/4 moonshine-zh 语音识别模型")
    try:
        from moonshine_voice.download import get_model_for_language
        cached_path, arch = get_model_for_language(
            "zh", on_progress=lambda f, m: print(
                f"\r    {f*100:3.0f}%  {m}", end="", flush=True))
        print()
        dst = MODELS / "moonshine-zh"
        if Path(cached_path).resolve() != dst.resolve():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(cached_path, dst)
        print(f"  ✓ 就绪: {dst}")
    except Exception as e:
        print(f"\n  ✗ moonshine-zh 下载失败: {e}")
        print("    （该模型也可手动下载：见 README「模型下载」一节）")
        raise

    # ── 2. opus-mt-zh-en (CT2 int8) ──
    step("2/4 opus-mt-zh-en 翻译模型（CTranslate2 int8）")
    dst = MODELS / "opus-mt-zh-en-ct2-int8"
    if REPO_RELEASE_URL:
        import tempfile, zipfile
        z = Path(tempfile.gettempdir()) / "opus-mt-zh-en-ct2-int8.zip"
        download(REPO_RELEASE_URL, z, "opus-mt int8 离线包")
        with zipfile.ZipFile(z) as f:
            f.extractall(MODELS)
        print(f"  ✓ 解压就绪: {dst}")
    else:
        # 从 HF 镜像下原始模型，提示用 convert_opus_mt.py 自行转换
        base = f"{HF_ENDPOINT}/Helsinki-NLP/opus-mt-zh-en/resolve/main"
        raw = PROJ / "test_output" / "_opus_mt_raw"
        download(f"{base}/config.json", raw / "config.json", "config.json")
        download(f"{base}/pytorch_model.bin", raw / "pytorch_model.bin",
                 "pytorch_model.bin (~310MB)")
        download(f"{base}/source.spm", raw / "source.spm", "source.spm")
        download(f"{base}/target.spm", raw / "target.spm", "target.spm")
        download(f"{base}/vocab.json", raw / "vocab.json", "vocab.json")
        print("  ✓ 原始模型已下载，正在转换 int8（需临时安装 ctranslate2+transformers）……")
        _convert_opus(raw, dst)
        print(f"  ✓ 转换就绪: {dst}")

    # ── 3. TinyTTS ──
    step("3/4 TinyTTS 语音合成模型")
    base = f"{HF_ENDPOINT}/moonshineai/tiny-tts/resolve/main"
    for f in ("text_encoder.onnx", "duration_predictor.onnx",
              "flow.onnx", "decoder.onnx"):
        download(f"{base}/{f}", MODELS / "tinytts-onnx" / f, f)

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
    r = subprocess.run([sys.executable,
                        str(PROJ / "scripts" / "convert_opus_mt.py")],
                       cwd=str(PROJ))
    if r.returncode != 0 or not dst.exists():
        raise RuntimeError("opus-mt 转换失败，可手动运行 scripts/convert_opus_mt.py")


if __name__ == "__main__":
    main()
