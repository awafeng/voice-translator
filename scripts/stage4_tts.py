# -*- coding: utf-8 -*-
"""阶段4 测试：语音合成（TTS）独立验证。

用法：
  双击 4A bat    合成 4 句英文并从默认扬声器播放（听完判断音质）
  双击 4B bat    打字输入英文合成播放（交互）
"""
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

OUT_DIR = PROJ / "test_output"

TEST_SENTENCES = [
    "It's a lovely day. Let's go for a walk in the park.",
    "Where's the nearest subway station?",
    "You played a great game. Let's play together.",
    "I will go to the supermarket to buy some things.",
]

args = sys.argv[1:]


def main():
    print("=" * 60)
    print("阶段4：语音合成（TinyTTS ONNX）独立验证")
    print("=" * 60)

    from tts import create_default_tts

    engine = create_default_tts()
    print(f"引擎：{type(engine).__name__}")
    print("加载模型……")
    t0 = time.time()
    engine.load()
    print(f"模型加载完成，耗时 {time.time()-t0:.1f} 秒\n")

    OUT_DIR.mkdir(exist_ok=True)

    if "--interactive" in args:
        print("交互模式：输入英文回车合成播放，输入 q 退出。\n")
        import sounddevice as sd
        while True:
            s = input("English> ").strip()
            if s.lower() in ("q", "quit", "exit", ""):
                break
            t0 = time.time()
            audio, sr = engine.synthesize(s)
            print(f"（合成耗时 {(time.time()-t0)*1000:.0f} ms，音频 {len(audio)/sr:.1f} 秒）")
            sd.play(audio, sr)
            sd.wait()
        engine.close()
        return

    import sounddevice as sd

    total_rt = 0.0
    for i, s in enumerate(TEST_SENTENCES):
        print(f"第 {i+1} 句：{s}")
        t0 = time.time()
        audio, sr = engine.synthesize(s)
        dt = time.time() - t0
        total_rt += dt
        wav_path = OUT_DIR / f"tts_sample_{i}.wav"
        import soundfile as sf
        sf.write(wav_path, audio, sr)
        print(f"  合成耗时 {dt*1000:.0f} ms -> 音频 {len(audio)/sr:.2f} 秒"
              f"（实时率 {len(audio)/sr/max(dt,1e-9):.0f}x），已存 {wav_path.name}")
        print(f"  现在播放……")
        sd.play(audio, sr)
        sd.wait()
        print()

    engine.close()
    print("=" * 60)
    print("请听上面的 4 段音频，判断音质能否接受。")
    print("音质不理想也正常——TinyTTS 只有 1.6M 参数，是所有候选里最小的；")
    print("可换 Piper(63M)/KittenTTS(10M) 等，音质更好但更大更慢。")
    print("=" * 60)


if __name__ == "__main__":
    main()
