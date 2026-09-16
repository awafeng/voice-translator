# -*- coding: utf-8 -*-
"""压力测试：完整流水线（STT→MT→TTS）循环 N 轮，验证进程稳定性。

用途：排查"莫名闪退"（堆损坏 0xc0000374）。堆损坏通常在
内存反复分配/释放 + 多线程竞争时才撞出来，跑得越多越接近真实。

用法：
  venv\\Scripts\\python.exe scripts\\stress_test.py --rounds 30
  --rounds N   循环轮数（默认 30）
  --threads K  并发流水线线程数（默认 1；>1 时模拟多句同时到）
  --exe PATH   改测打包版 exe（--selftest 机制外的独立压测入口）
"""
import argparse
import os
import random
import subprocess
import sys
import time
import wave
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SR = 16000
OUT_DIR = PROJ / "test_output"


def synth_zh_sentence(text, out_path):
    """用 Windows Huihui 合成"模拟用户说的话"。"""
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


import numpy as np  # noqa: E402  (load_wav_mono 里用到，放后面统一)

SENTENCES = [
    "今天天气真好，我们去公园散步吧。",
    "请问最近的地铁站在哪里？",
    "你的游戏打得真不错，我们一起玩吧。",
    "我这边网络有点卡，你那边呢？",
    "等一下，我先喝口水。",
    "这个boss太难了，我们换个打法。",
    "左转左转，有人在门口蹲着。",
    "我先下线了，明天再玩。",
]


def prepare_inputs(n):
    """准备 n 段不同的输入音频（循环使用语料，变化足够）。"""
    OUT_DIR.mkdir(exist_ok=True)
    clips = []
    for i in range(n):
        text = SENTENCES[i % len(SENTENCES)]
        wav = OUT_DIR / f"_stress_in_{i % len(SENTENCES)}.wav"
        if not wav.exists():
            if not synth_zh_sentence(text, wav):
                raise RuntimeError("模拟语音合成失败")
        a, sr = load_wav_mono(wav)
        # 每轮加轻微随机偏移，避免识别端缓存任何东西
        shift = random.randint(0, sr // 10)
        a = np.roll(a, shift)
        clips.append(a)
    return clips


def run_inproc(rounds, threads):
    """源码环境压测：加载三引擎后循环 跑 rounds 轮流水线。"""
    from audio.pipeline import TranslationPipeline
    from stt import create_default_stt
    from translation import create_default_translator
    from tts import create_default_tts

    print("加载三模型……")
    pipe = TranslationPipeline(
        stt=create_default_stt(),
        translator=create_default_translator(),
        tts=create_default_tts(),
    )
    t0 = time.time()
    pipe.load_all()
    print(f"加载完成 {time.time()-t0:.1f}s，开始压测 {rounds} 轮 x {threads} 线程")

    clips = prepare_inputs(min(len(SENTENCES), max(3, rounds)))

    ok_cnt = err_cnt = 0
    t0 = time.time()
    import threading

    def worker(tid):
        nonlocal ok_cnt, err_cnt
        for r in range(rounds):
            a = clips[(r + tid) % len(clips)]
            try:
                _, _, ev = pipe.process_speech(a, SR)
                if ev.ok:
                    ok_cnt += 1
                else:
                    err_cnt += 1
                    print(f"  [t{tid} r{r}] 失败: {ev.error}")
            except Exception as e:
                err_cnt += 1
                print(f"  [t{tid} r{r}] 异常: {e}")
            time.sleep(0.05)

    ths = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    dt = time.time() - t0
    print(f"完成: 成功 {ok_cnt} / 失败 {err_cnt} / 用时 {dt:.1f}s "
          f"({dt/max(1, ok_cnt+err_cnt):.2f}s/轮)")
    pipe.close()
    return 0 if err_cnt == 0 else 1


def run_exe(exe_path, rounds):
    """打包 exe 压测：exe 没有 CLI 压测入口，用 --selftest 连跑 N 次。
    每次都是全新进程加载全部模型+跑一遍链路，足以暴露加载期崩溃。"""
    exe_path = Path(exe_path)
    fails = 0
    for i in range(rounds):
        t0 = time.time()
        p = subprocess.run([str(exe_path), "--selftest"],
                           cwd=str(exe_path.parent),
                           capture_output=True, text=True, timeout=300)
        dt = time.time() - t0
        status = "OK" if p.returncode == 0 else f"FAIL(code={p.returncode})"
        print(f"  round {i+1}/{rounds}: {status}  {dt:.1f}s")
        if p.returncode != 0:
            fails += 1
            print("    stdout:", p.stdout[-500:])
            print("    stderr:", p.stderr[-500:])
    print(f"exe 压测完成: {rounds - fails}/{rounds} 通过")
    return 0 if fails == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=30)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--exe", type=str, default=None)
    args = ap.parse_args()

    if args.exe:
        code = run_exe(args.exe, args.rounds)
    else:
        code = run_inproc(args.rounds, args.threads)
    sys.exit(code)


if __name__ == "__main__":
    main()
