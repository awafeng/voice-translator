# -*- coding: utf-8 -*-
"""阶段2 测试：语音识别（STT）独立验证。

用法：
  双击 2A bat  —— 用系统自带中文语音合成"标准测试句"来测识别（无需麦克风）
  双击 2B bat  —— 从麦克风录音来测识别（需要麦克风）
  python stage2_stt.py --file 某文件.wav   识别一个现成的 wav 文件
"""
import sys
import time
import wave
from pathlib import Path

import numpy as np

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SR = 16000
OUT_DIR = PROJ / "test_output"

args = sys.argv[1:]


def get_opt(flag, default=None):
    if flag in args:
        i = args.index(flag)
        return args[i + 1] if i + 1 < len(args) else None
    return default


def synth_test_sentences():
    """用 Windows 自带的中文语音(Huihui)合成3句标准测试语音。"""
    import soundfile as sf  # noqa: F401  确保可用
    import subprocess

    sentences = [
        "今天天气真好，我们去公园散步吧。",
        "这个软件可以把中文翻译成英文。",
        "请问最近的地铁站在哪里？",
    ]
    wavs = []
    for idx, s in enumerate(sentences):
        raw = OUT_DIR / f"_tts_ref_{idx}.wav"
        ps = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Add-Type -AssemblyName System.Speech;"
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                f"$s.SetOutputToWaveFile('{raw}');"
                f"$s.SelectVoice('Microsoft Huihui Desktop');"
                "$s.Rate = -1;"  # 语速放慢一点，更像自然说话
                f"$s.Speak('{s}');"
                "$s.Dispose()",
            ],
            capture_output=True, text=True,
        )
        if ps.returncode != 0 or not raw.exists():
            print(f"  合成第{idx+1}句失败：{ps.stderr}")
            continue
        wavs.append((raw, s))
    return wavs


def load_wav_mono(path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        data = w.readframes(n)
    if sw == 2:
        a = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        a = np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"不支持的采样宽度 {sw}")
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def main():
    print("=" * 60)
    print("阶段2：语音识别（Moonshine 普通话）独立验证")
    print("=" * 60)

    from stt import create_default_stt

    engine = create_default_stt()
    print(f"引擎：{type(engine).__name__}")
    print("加载模型……")
    t0 = time.time()
    engine.load()
    print(f"模型加载完成，耗时 {time.time()-t0:.1f} 秒")

    mode = None
    if get_opt("--file"):
        mode = "file"
    elif "--mic" in args:
        mode = "mic"
    else:
        mode = "auto"

    results = []

    if mode == "file":
        import soundfile as sf
        path = Path(get_opt("--file"))
        audio, sr = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        print(f"\n识别文件：{path.name}（{len(audio)/sr:.1f} 秒）")
        t0 = time.time()
        text = engine.transcribe_file(audio, sr)
        dt = time.time() - t0
        print(f"识别结果：{text}")
        print(f"（耗时 {dt:.2f} 秒，音频 {len(audio)/sr:.2f} 秒）")
        results.append((path.name, text))

    elif mode == "mic":
        import sounddevice as sd
        print("\n请准备说话。")
        for i in (3, 2, 1):
            print(f"  {i}…")
            time.sleep(1)
        print("开始录音（5秒）——请说中文！")
        rec = sd.rec(int(5 * SR), samplerate=SR, channels=1, dtype="float32")
        sd.wait()
        print("录音结束，开始识别……")
        t0 = time.time()
        text = engine.transcribe_file(rec.mean(axis=1), SR)
        dt = time.time() - t0
        print(f"识别结果：{text}")
        print(f"（耗时 {dt:.2f} 秒）")
        results.append(("麦克风录音", text))

    else:  # auto: SAPI 合成测试句
        print("\n方式：用 Windows 自带中文语音合成3句标准测试语音（无需麦克风）")
        OUT_DIR.mkdir(exist_ok=True)
        wavs = synth_test_sentences()
        if not wavs:
            print("✗ 合成测试语音失败，改用 --file 或 --mic 模式。")
            sys.exit(1)
        for raw, ref in wavs:
            audio, sr = load_wav_mono(raw)
            print(f"\n第 {len(results)+1} 句（标准答案）：{ref}")
            t0 = time.time()
            text = engine.transcribe_file(audio, sr)
            dt = time.time() - t0
            print(f"识别结果：{text}")
            print(f"（耗时 {dt:.2f} 秒，音频 {len(audio)/sr:.2f} 秒）")
            results.append((ref, text))

    print()
    print("=" * 60)
    print("汇总：")
    for ref, got in results:
        print(f"  原句：{ref}")
        print(f"  识别：{got}")
        print(f"  {'-' * 50}")
    engine.close()
    print("如果识别结果和原句基本一致（个别错字可接受），阶段2 通过。")
    print("=" * 60)


if __name__ == "__main__":
    main()
