# -*- coding: utf-8 -*-
"""阶段6 测试：流水线输出 → 虚拟声卡 + 本地回放开关。

模式：
  双击 6A bat   自动模式：3句模拟中文 → 完整流水线 → 英文发到虚拟声卡
                播放前会问你要不要开本地回放（想听就开）
  双击 6B bat   麦克风模式（需要麦克风）
  --playback / --no-playback  跳过询问，直接指定本地回放开/关
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
    print("阶段6：流水线 → 虚拟声卡 + 本地回放开关")
    print("=" * 60)

    from audio.pipeline import TranslationPipeline
    from audio.output import OutputManager
    from stt import create_default_stt
    from translation import create_default_translator
    from tts import create_default_tts

    out_mgr = OutputManager()
    dev = out_mgr.find_cable_output()
    if dev is None:
        print("✗ 未找到虚拟声卡，请先安装 VB-CABLE 再运行本测试。")
        sys.exit(1)
    dev_name = None
    import sounddevice as sd
    dev_name = sd.query_devices(dev)["name"]
    print(f"虚拟声卡输出端：#{dev}「{dev_name}」")

    # 本地回放开关
    if "--playback" in args:
        local_pb = True
    elif "--no-playback" in args:
        local_pb = False
    else:
        ans = input("是否开启本地回放？（开=你也能从耳机听到英文；"
                    "关=只发给虚拟声卡）[y/N] ").strip().lower()
        local_pb = ans in ("y", "yes", "开", "1")
    out_mgr.set_local_playback(local_pb)
    print(f"本地回放：{'开' if local_pb else '关'}\n")

    pipe = TranslationPipeline(
        stt=create_default_stt(),
        translator=create_default_translator(),
        tts=create_default_tts(),
        debug=True,
    )
    print("加载三个模型……")
    dt = pipe.load_all()
    print(f"全部加载完成，耗时 {dt:.1f} 秒\n")

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
        rec = sd.rec(int(5 * SR), samplerate=SR, channels=1, dtype="float32")
        sd.wait()
        print("录音结束\n")
        cases.append(("麦克风录音", rec.mean(axis=1), SR))
    else:
        sentences = [
            "今天天气真好，我们去公园散步吧。",
            "请问最近的地铁站在哪里？",
            "你的游戏打得真不错，我们一起玩吧。",
        ]
        OUT_DIR.mkdir(exist_ok=True)
        print("自动模式：用系统中文语音模拟'你说的话'\n")
        for i, s in enumerate(sentences):
            wav = OUT_DIR / f"_stage6_in_{i}.wav"
            if synth_zh_sentence(s, wav):
                a, sr = load_wav_mono(wav)
                cases.append((s, a, sr))

    if not cases:
        print("✗ 没有可用测试输入")
        sys.exit(1)

    print()
    for label, audio, sr in cases:
        print(f"▶ 测试：{label}")
        audio_out, sr_out, ev = pipe.process_speech(audio, sr)
        if ev.ok:
            print(f"  识别：{ev.zh_text}")
            print(f"  翻译：{ev.en_text}")
            parts = "  ".join(f"{k} {v:.0f}ms" for k, v in ev.stages_ms.items())
            print(f"  耗时：{parts} | 总 {ev.total_ms:.0f} ms")
            print(f"  → 正在发送到虚拟声卡"
                  f"{'（+本地回放）' if local_pb else ''}……")
            out_mgr.play_to_cable(audio_out, sr_out)
            print("  ✓ 已发送完毕")
        else:
            print(f"  ✗ 失败：{ev.error}")
        print("-" * 56)

    pipe.close()
    out_mgr.close()
    print()
    print("=" * 60)
    print("本机验证到此结束。最终验证方式：")
    print("  Discord → 设置 → 语音和视频 → 输入设备选「CABLE Output (VB-Audio Point)」")
    print("  然后运行本脚本，看 Discord 麦克风测试条是否随英文语音跳动；")
    print("  或直接语音通话给好友/回音室测试。")
    print("=" * 60)


if __name__ == "__main__":
    main()
