# -*- coding: utf-8 -*-
"""阶段1 测试B：麦克风采集验证 + 播放到虚拟声卡。

用法（在命令行里选一种，或直接双击对应 .bat）：
  python stage1_mic.py                    交互式：列出设备让你选
  python stage1_mic.py --device 3         直接指定输入设备编号
  python stage1_mic.py --device 3 --seconds 6
  python stage1_mic.py --file xx.wav      跳过录音，用现成的 wav 文件测后半段
  python stage1_mic.py --volume 0.5       播放到虚拟声卡时的音量 (0.0~1.0)
  python stage1_mic.py --speakers        同时也从默认扬声器播放（听到自己）
"""
import sys
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SR = 16000
CHANNELS = 1
SECONDS = 5
SKIP_PLAYBACK = "--skip-playback" in sys.argv
OUT_DIR = Path(__file__).resolve().parent.parent / "test_output"
args = sys.argv[1:]


def get_opt(flag, default=None):
    if flag in args:
        i = args.index(flag)
        return args[i + 1] if i + 1 < len(args) else None
    return default


DEV = get_opt("--device")
SEC = float(get_opt("--seconds", SECONDS))
VOL = float(get_opt("--volume", 1.0))
FILE = get_opt("--file")
ALSO_SPEAKERS = "--speakers" in args


def list_inputs():
    return [
        (i, d["name"], d["max_input_channels"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


def list_cable_outs():
    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_output_channels"] > 0
        and ("cable" in d["name"].lower() or "vb-audio" in d["name"].lower())
    ]


def record(dev, seconds):
    print(f"开始录音 {seconds:.0f} 秒，请对着设备说话/放歌……")
    for i in (3, 2, 1):
        print(f"  {i}…")
        time.sleep(1)
    rec = sd.rec(
        int(seconds * SR), samplerate=SR, channels=CHANNELS,
        device=dev, dtype="float32",
    )
    sd.wait()
    mono = rec.mean(axis=1)
    peak = float(np.max(np.abs(mono)))
    print(f"录音结束。信号峰值：{peak:.3f} (0.005 以下算没声音，0.5 以上算爆音)")
    return mono, peak


def save_wav(path, data, sr):
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def play_to(dev, data, sr, volume=1.0, block=True):
    sig = data * volume
    if block:
        sd.play(sig, sr, device=dev)
        sd.wait()
    else:
        sd.play(sig, sr, device=dev)


def main():
    print("=" * 60)
    print("阶段1 测试B：麦克风采集 → 播放到虚拟声卡")
    print("=" * 60)

    # ── 第一步：确定录音来源 ─────────────────────────────
    if FILE:
        import soundfile as sf
        data, sr = sf.read(FILE, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        print(f"使用现成文件：{FILE}")
        mono = data if sr == SR else None
        if mono is None:
            ratio = sr / SR
            n = int(len(data) / ratio)
            idx = np.minimum((np.arange(n) * ratio).astype(np.int64), len(data) - 1)
            mono = data[idx]
        peak = float(np.max(np.abs(mono)))
        print(f"文件长度 {len(mono)/SR:.1f} 秒，峰值 {peak:.3f}")
    else:
        inputs = list_inputs()
        if not inputs:
            print("✗ 没有任何输入设备，无法录音。")
            sys.exit(1)
        if DEV is None:
            print("【输入设备列表】")
            for i, name, ch in inputs:
                print(f"  #{i}: {name} ({ch}声道)")
            print()
            raw = input("请输入要测试的设备编号（等号左边的数字）后回车：").strip()
            DEV = raw
        try:
            dev_i = int(DEV)
            dev_name = sd.query_devices(dev_i)["name"]
        except Exception:
            print(f"✗ 无法识别的设备编号：{DEV}")
            sys.exit(1)
        print(f"选定设备 #{dev_i}「{dev_name}」")
        mono, peak = record(dev_i, SEC)
        if peak < 0.005:
            print("⚠ 录到的声音几乎为零，请检查：设备是否选对、麦克风是否被静音。")

    # ── 第二步：保存录音 ────────────────────────────────
    OUT_DIR.mkdir(exist_ok=True)
    wav = OUT_DIR / "my_voice.wav"
    save_wav(wav, mono, SR)
    print(f"你的录音已保存：{wav}")

    # ── 第三步：播放到虚拟声卡 ────────────────────────────
    outs = list_cable_outs()
    if not outs:
        print("✗ 没找到虚拟声卡播放端，请先安装 VB-CABLE。")
        sys.exit(1)
    oi, oname = outs[0]
    print()
    print(f"现在把这段录音播放到虚拟声卡「{oname}」。")
    if SKIP_PLAYBACK:
        print("  （--skip-playback：只保存，不播放）")
    else:
        play_to(oi, mono, SR, VOL)
        print("  ✓ 已播放到虚拟声卡。")
        if ALSO_SPEAKERS:
            print("  同时从默认扬声器播放，你现在应该能听到自己的声音。")
            sd.play(mono, SR)
            sd.wait()

    print()
    print("=" * 60)
    print("本机测试到此结束。")
    print("最终验证要靠 Discord：Discord → 设置 → 麦克风选「CABLE Output」，")
    print("运行本脚本后对着它说话，看 Discord 的音量条有没有跳动/能否听到声音。")
    print("=" * 60)


if __name__ == "__main__":
    main()
