# -*- coding: utf-8 -*-
"""阶段1 测试A：虚拟声卡链路回环验证（不需要麦克风）。

原理：往 "CABLE Input"（虚拟声卡的入口）播放一段“叮-咚”提示音，
     同时从 "CABLE Output"（虚拟声卡的出口）录音。
     如果录到的声音有信号，说明整条链路是通的——
     将来 Discord 从 CABLE Output 收声音，和我们这个测试做的是同一件事。
     最后把录到的声音从默认扬声器播放一次，让你亲耳听到它真的过去了。
"""
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SR = 48000
TONE_DUR = 4.0          # 提示音长度
LEAD = 0.5             # 录音提前量/收尾
TOTAL = TONE_DUR + 2 * LEAD
OUT_DIR = Path(__file__).resolve().parent.parent / "test_output"
SKIP_PLAYBACK = "--skip-playback" in sys.argv


def make_tone():
    """生成一段“叮-咚”提示音（C5 → E5），带淡入淡出。"""
    t = np.arange(int(TONE_DUR * SR)) / SR
    sig = np.zeros_like(t)
    m1 = t < 1.2
    sig[m1] = np.sin(2 * np.pi * 523.25 * t[m1])
    m2 = (t >= 1.6) & (t < 3.2)
    sig[m2] = np.sin(2 * np.pi * 659.25 * t[m2])
    env = np.minimum(1.0, np.minimum(t, TONE_DUR - t) / 0.05)
    return sig * env * 0.4


def cable_outputs():
    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_output_channels"] > 0
        and ("cable" in d["name"].lower() or "vb-audio" in d["name"].lower())
    ]


def cable_inputs():
    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
        and ("cable" in d["name"].lower() or "vb-audio" in d["name"].lower())
    ]


def loopback(out_dev, in_dev):
    """向 out_dev 播放提示音，同时从 in_dev 录音，返回(录音, 峰值)。"""
    tone = make_tone()
    pos = 0
    chunks = []

    def out_cb(outdata, frames, time_info, status):
        nonlocal pos
        need = min(frames, len(tone) - pos)
        outdata[:need, 0] = tone[pos:pos + need]
        outdata[need:, 0] = 0.0
        outdata[:, 1] = outdata[:, 0]
        pos += need

    def in_cb(indata, frames, time_info, status):
        chunks.append(indata.copy())

    rec_result = {}

    with sd.InputStream(device=in_dev, samplerate=SR, channels=2, callback=in_cb) as istream:
        with sd.OutputStream(device=out_dev, samplerate=SR, channels=2, callback=out_cb) as ostream:
            ostream.start()
            istream.start()
            t0 = time.time()
            while time.time() - t0 < TOTAL:
                time.sleep(0.1)
            istream.stop()
            ostream.stop()

    if not chunks:
        return None, 0.0
    rec = np.concatenate(chunks)
    mono = rec.mean(axis=1)
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    return mono, peak


def main():
    print("=" * 60)
    print("阶段1 测试A：虚拟声卡链路回环（无需麦克风）")
    print("=" * 60)

    outs = cable_outputs()
    ins = cable_inputs()
    if not outs:
        print("没找到虚拟声卡的播放端（CABLE Input），请先安装 VB-CABLE。")
        sys.exit(1)
    if not ins:
        print("没找到虚拟声卡的录音端（CABLE Output），请先安装 VB-CABLE。")
        sys.exit(1)

    print(f"候选播放端：{outs}")
    print(f"候选录音端：{ins}")
    print()

    success = False
    best_rec = None
    for oi, oname in outs:
        for ii, iname in ins:
            print(f"尝试：播放到「{oname}」 ←同时→ 从「{iname}」录音 ...")
            try:
                rec, peak = loopback(oi, ii)
            except Exception as e:
                print(f"  打开设备失败，跳过：{e}")
                continue
            print(f"  录到信号强度（峰值）：{peak:.3f}  (大于 0.01 算成功)")
            if peak > 0.01:
                best_rec = rec
                print(f"  ✓ 链路通了！声音成功穿过虚拟声卡。")
                success = True
                break
            time.sleep(0.3)
        if success:
            break

    print()
    if not success:
        print("✗ 所有设备组合都没录到信号。请把本窗口截图发给 Claude Code。")
        sys.exit(1)

    OUT_DIR.mkdir(exist_ok=True)
    wav = OUT_DIR / "loopback.wav"
    sf.write(wav, best_rec, SR)
    print(f"录音已保存：{wav}")

    if SKIP_PLAYBACK:
        print("（跳过扬声器回放步骤）")
    else:
        print()
        print("现在把录到的声音从默认扬声器播放一次，你应该能听到“叮-咚”。")
        for i in (3, 2, 1):
            print(f"  {i} 秒后开始播放...")
            time.sleep(1)
        sd.play(best_rec, SR)
        sd.wait()

    print()
    print("=" * 60)
    print("结论：虚拟声卡链路已打通。")
    print("（Discord 将来就是从 CABLE Output 收听我们的英文语音）")
    print("=" * 60)


if __name__ == "__main__":
    main()
