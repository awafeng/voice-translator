# -*- coding: utf-8 -*-
"""阶段7 测试：VAD 分段 + 实时流水线 + 延迟测量。

模式：
  双击 7A bat   自动模式：模拟"边说边喂音频"（无需麦克风），
                实测分段触发和端到端延迟
  双击 7B bat   麦克风实时模式（需要麦克风）：说几句中文，停顿后自动出英文
  --bench       纯延迟基准（不播放，逐句报数字）
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


def build_engine(debug=True, on_event=None):
    from audio.live_engine import LiveEngine
    from audio.output import OutputManager
    from audio.pipeline import TranslationPipeline
    from stt import create_default_stt
    from translation import create_default_translator
    from tts import create_default_tts

    out_mgr = OutputManager(volume=0.9, local_playback=False)
    pipe = TranslationPipeline(
        stt=create_default_stt(),
        translator=create_default_translator(),
        tts=create_default_tts(),
        debug=debug,
    )
    print("加载三个模型 + VAD……")
    dt = pipe.load_all()
    print(f"全部加载完成，耗时 {dt:.1f} 秒")
    use_mic = "--mic" in args
    eng = LiveEngine(pipe, out_mgr, debug=debug, on_event=on_event,
                     use_mic=use_mic)
    return eng, pipe


def main():
    print("=" * 60)
    print("阶段7：VAD 分段 + 实时流水线 + 延迟测量")
    print("=" * 60)

    if "--bench" in args:
        bench_mode = True
    else:
        bench_mode = False

    events = []

    def on_event(ev):
        events.append(ev)
        if ev.get("ok"):
            print(f"\n  [事件] 中→{ev['zh']} → 英→{ev['en']}")
            st = ev.get("stages_ms", {})
            parts = " ".join(f"{k}={v:.0f}ms" for k, v in st.items())
            print(f"  [耗时] {parts} 总处理={ev['total_ms']:.0f}ms")
            d = ev.get("first_audio_delay_ms")
            if d:
                print(f"  [延迟] 句尾→英文出声: {d:.0f} ms（含静音判定 450ms）")
        else:
            print(f"\n  [事件] 失败：{ev.get('error')}")

    eng, pipe = build_engine(debug=not bench_mode, on_event=on_event)

    if get_opt("--file"):
        # 单文件模式：喂一个 wav，看 VAD 怎么切
        path = Path(get_opt("--file"))
        audio, sr = load_wav_mono(path)
        if sr != SR:
            print(f"⚠ 文件采样率 {sr} != 16k，请提供 16k wav")
            sys.exit(1)
        print(f"\n喂入文件 {path.name}（{len(audio)/SR:.1f} 秒），实时播放速度喂入……")
        run_simulation(eng, [(audio, None)], bench_mode)
        return

    if "--mic" in args:
        print("\n实时模式：现在开始监听（Ctrl+C 或按回车停止）")
        print("说话方式：说一句 → 停顿约 0.6 秒 → 软件自动处理并出英文\n")
        eng.start()
        try:
            input()
        except KeyboardInterrupt:
            pass
        eng.stop()
        report(events)
        return

    # 自动模式：合成三句，模拟"边说边喂"
    sentences = [
        "今天天气真好，我们去公园散步吧。",
        "请问最近的地铁站在哪里？",
        "你的游戏打得真不错，我们一起玩吧。",
    ]
    OUT_DIR.mkdir(exist_ok=True)
    prepared = []
    for i, s in enumerate(sentences):
        wav = OUT_DIR / f"_stage7_in_{i}.wav"
        if not wav.exists():
            synth_zh_sentence(s, wav)
        a, sr = load_wav_mono(wav)
        prepared.append((a, s))

    print("\n自动模式：以真实时间流速喂入三句模拟语音（句间停顿 1 秒）")
    run_simulation(eng, prepared, bench_mode)
    report(events)


def run_simulation(eng, prepared, bench_mode):
    """按真实播放速度喂音频（32ms 一块），模拟麦克风实时输入。"""
    import threading

    eng.start()
    done = threading.Event()

    def feeder():
        for audio, _label in prepared:
            block = 512
            for i in range(0, len(audio), block):
                if not eng._running:
                    return
                eng._audio_q.put(audio[i:i + block].reshape(-1, 1).astype(np.float32))
                time.sleep(0.032)  # 真实时速
            time.sleep(1.0)  # 句间停顿
        # 等最后一句的处理完成
        time.sleep(2.0)

    th = threading.Thread(target=feeder, daemon=True)
    th.start()
    th.join()

    # 等待所有队列任务处理完
    while not eng._audio_q.empty() or getattr(eng, "_processing_lock").locked():
        time.sleep(0.2)
    time.sleep(0.5)
    eng.stop()
    print()


def report(events):
    print("=" * 60)
    ok_events = [e for e in events if e.get("ok")]
    print(f"结果：{len(ok_events)}/{len(events)} 句成功")
    if ok_events:
        ds = [e["first_audio_delay_ms"] for e in ok_events
              if e.get("first_audio_delay_ms")]
        if ds:
            print(f"端到端延迟（句尾→英文出声）：")
            print(f"  最快 {min(ds):.0f} ms | 平均 {sum(ds)/len(ds):.0f} ms | "
                  f"最慢 {max(ds):.0f} ms")
            print(f"  目标 <2000 ms：{'达标' if max(ds) < 2000 else '未达标'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
