# -*- coding: utf-8 -*-
"""阶段3 测试：机器翻译独立验证。

用法：
  双击 3-翻译测试.bat          用内置测试句测试
  python stage3_translate.py   同上
  python stage3_translate.py --interactive   手动打字交互测试
"""
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

TEST_SENTENCES = [
    "今天天气真好，我们去公园散步吧。",
    "这个软件可以把中文翻译成英文。",
    "请问最近的地铁站在哪里？",
    "我等一下要去超市买点东西。",
    "你的游戏打得真不错，我们一起玩吧。",
    "现在几点了？我马上要开会了。",
    "这道菜太好吃了，我想再要一份。",
    "我的电脑昨天坏了，今天刚修好。",
]


def main():
    print("=" * 60)
    print("阶段3：机器翻译（opus-mt-zh-en, CTranslate2 int8）独立验证")
    print("=" * 60)

    from translation import create_default_translator

    engine = create_default_translator()
    print(f"引擎：{type(engine).__name__}")
    print("加载模型……")
    t0 = time.time()
    engine.load()
    print(f"模型加载完成，耗时 {time.time()-t0:.1f} 秒\n")

    if "--interactive" in sys.argv:
        print("交互模式：输入中文回车翻译，输入 q 回车退出。\n")
        while True:
            s = input("中文> ").strip()
            if s.lower() in ("q", "quit", "exit", ""):
                break
            t0 = time.time()
            out = engine.translate(s)
            print(f"英文> {out}   （{time.time()-t0:.2f} 秒）\n")
        engine.close()
        return

    total_time = 0.0
    for s in TEST_SENTENCES:
        t0 = time.time()
        out = engine.translate(s)
        dt = time.time() - t0
        total_time += dt
        print(f"中文：{s}")
        print(f"英文：{out}")
        print(f"（{dt*1000:.0f} 毫秒）")
        print("-" * 50)

    print(f"8 句平均：{total_time/len(TEST_SENTENCES)*1000:.0f} 毫秒/句")
    engine.close()
    print()
    print("如果翻译结果通顺达意（不要求逐字对应），阶段3 通过。")
    print("=" * 60)


if __name__ == "__main__":
    main()
