# -*- coding: utf-8 -*-
"""阶段0 环境自检脚本：验证开发环境搭建成功、且没有误装重型库。"""
import sys
import importlib.util

# Windows 控制台中文输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

FAILED = []


def check(name, ok, detail=""):
    mark = "通过" if ok else "失败"
    print(f"  [{mark}] {name}" + (f" —— {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


print("=" * 56)
print("实时中译英语音翻译软件 —— 阶段0 环境自检")
print("=" * 56)

# 1. Python 版本
v = sys.version_info
check("Python 版本", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}")

# 2. 核心推理库（带实测导入运行）
print()
print("核心库导入测试：")
try:
    import numpy

    check("numpy", True, f"v{numpy.__version__}")
except Exception as e:
    check("numpy", False, str(e))

try:
    import onnxruntime as ort

    providers = ort.get_available_providers()
    check("onnxruntime", True, f"v{ort.__version__}，可用引擎：{providers}")
except Exception as e:
    check("onnxruntime", False, str(e))

try:
    import ctranslate2

    check("ctranslate2", True, f"v{ctranslate2.__version__}")
except Exception as e:
    check("ctranslate2", False, str(e))

# 3. 音频库
print()
print("音频库导入测试：")
try:
    import sounddevice

    check("sounddevice（麦克风采集用）", True, f"v{sounddevice.__version__}")
except Exception as e:
    check("sounddevice", False, str(e))

try:
    import soundfile

    check("soundfile（音频文件读写用）", True, f"v{soundfile.__version__}")
except Exception as e:
    check("soundfile", False, str(e))

# 4. 确认禁止项：不能装了 PyTorch / TensorFlow / JAX
print()
print("重型库检查（必须全部显示“未安装”）：")
for lib in ("torch", "tensorflow", "jax"):
    spec = importlib.util.find_spec(lib)
    check(f"{lib} 未安装", spec is None)

# 5. 列出所有已安装的包和总体积
print()
print("已安装的第三方库及体积：")
try:
    from pathlib import Path

    site = Path(sys.prefix) / "Lib" / "site-packages"
    total = 0.0
    rows = []
    for child in sorted(site.iterdir()):
        if child.name.startswith(("_", "pip", "setuptools", "wheel")):
            continue
        if child.is_dir():
            size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
        else:
            # .dist-info 单文件情况跳过（其体积已算进对应包目录）
            size = 0 if child.suffix == ".dist-info" else child.stat().st_size
        if size > 0:
            rows.append((child.name, size))
            total += size
    for name, size in rows:
        print(f"    {name:<28} {size / 1e6:7.1f} MB")
    print(f"  ------------------------------------------")
    print(f"  总计：{len(rows)} 个包，约 {total / 1e6:.0f} MB")
except Exception as e:
    print(f"  （体积统计出错：{e}）")

# 6. 结论
print()
print("=" * 56)
if FAILED:
    print(f"结果：{len(FAILED)} 项未通过 —— {', '.join(FAILED)}")
    print("请把上面的输出截图发给 Claude Code 排查。")
    sys.exit(1)
else:
    print("环境搭建成功！onnxruntime + ctranslate2 就绪，未安装 PyTorch。")
    print("可以进入阶段1（音频链路验证）。")
print("=" * 56)
