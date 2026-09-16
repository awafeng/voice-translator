# -*- coding: utf-8 -*-
"""阶段5 测试：完整流水线 说话→识别→翻译→合成→播放。

模式：
  双击 5A bat   自动模式：用中文语音合成"模拟用户说的话"驱动流水线（无需麦克风）
  双击 5B bat   麦克风模式：录5秒中文，走完整流水线（需要麦克风）
  --file xx.wav 用现成 wav 测试
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


def load_wav_mono(path):
    with wave.open(str(path), "rb") as w:
        sr, n, ch, sw = (w.getframerate(), w.getnframes(),
                         w.getnchannels(), w.getsampwidth())
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


def synth_zh_sentence(text, out_path):
    """用 Windows Huihui 合成'模拟用户说的话'。"""
    import subprocess

    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Add-Type -AssemblyName System.Speech;"
         f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
         f"$s.SetOutputToWaveFile('{out_path}');"
         "$s.SelectVoice('Microsoft Huihui Desktop');"
         "$s.Rate = -1;"
         f"$s.Speak('{text}');"
         "$s.Dispose()"],
        capture_output=True, text=True,
    )
    return ps.returncode == 0 and Path(out_path).exists()


def main():
    print("=" * 60)
    print("阶段5：完整流水线（STT→翻译→TTS→播放）")
    print("=" * 60)

    from audio.pipeline import TranslationPipeline
    from stt import create_default_stt
    from translation import create_default_translator
    from tts import create_default_tts

    pipe = TranslationPipeline(
        stt=create_default_stt(),
        translator=create_default_translator(),
        tts=create_default_tts(),
        debug=True,  # 调试模式：显示识别/翻译中间文字
    )
    print("加载三个模型……")
    dt = pipe.load_all()
    print(f"全部加载完成，耗时 {dt:.1f} 秒\n")

    import sounddevice as sd

    cases = []
    if get_opt("--file"):
        path = Path(get_opt("--file"))
        audio, sr = load_wav_mono(path)
        cases.append((f"文件:{path.name}", audio, sr))
    elif "--mic" in args:
        print("准备说话，倒数3秒后录5秒：")
        for i in (3, 2, 1):
            print(f"  {i}…")
            time.sleep(1)
        print("录音中——请说中文！")
        rec = sd.rec(int(5 * SR), samplerate=SR, channels=1, dtype="float32")
        sd.wait()
        print("录音结束\n")
        cases.append(("麦克风录音", rec.mean(axis=1), SR))
    else:
        # 自动模式：模拟用户说三句不同风格的中文
        sentences = [
            "今天天气真好，我们去公园散步吧。",
            "请问最近的地铁站在哪里？",
            "你的游戏打得真不错，我们一起玩吧。",
        ]
        OUT_DIR.mkdir(exist_ok=True)
        print("自动模式：用系统中文语音模拟'你说的话'（麦克风没插也能测）\n")
        for i, s in enumerate(sentences):
            wav = OUT_DIR / f"_stage5_in_{i}.wav"
            if synth_zh_sentence(s, wav):
                a, sr = load_wav_mono(wav)
                cases.append((s, a, sr))
            else:
                print(f"⚠ 模拟语音合成失败，跳过第{i+1}句")

    if not cases:
        print("✗ 没有可用测试输入")
        sys.exit(1)

    print()
    for label, audio, sr in cases:
        print(f"▶ 测试：{label}")
        t0 = time.time()
        audio_out, sr_out, ev = pipe.process_speech(audio, sr)
        # 播放等待时间也计入"感知延迟"的一部分
        if ev.ok:
            print(f"  你说的（识别）：{ev.zh_text}")
            print(f"  英文（翻译）：  {ev.en_text}")
            parts = "  ".join(
                f"{k} {v:.0f}ms" for k, v in ev.stages_ms.items()
            )
            print(f"  耗时：{parts}  | 处理总耗时 {ev.total_ms:.0f} ms")
            print(f"  现在播放合成英文（{len(audio_out)/sr_out:.1f} 秒）……")
            sd.play(audio_out, sr_out)
            sd.wait()
        else:
            print(f"  ✗ 失败：{ev.error}")
        print("-" * 56)

    pipe.close()
    print()
    print("=" * 60)
    print("总结：上面每句都是 完整中文语音 → 识别 → 翻译 → 英文语音。")
    print("不追求快，只追求对。三句都能对上，阶段5 通过。")
    print("=" * 60)


if __name__ == "__main__":
    main()
