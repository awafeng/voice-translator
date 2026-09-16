# -*- coding: utf-8 -*-
"""首次运行/启动环境自检（阶段11）。

逐项检查软件运行的前提条件，返回结构化结果：
  每项: {id, ok, level, title, problem, solution}
  level: "error"（必须解决，否则核心功能不可用）
         "warn" （能用，但有影响）
每次启动时后台静默跑一遍，全通过不弹窗；
有问题时 GUI 汇总弹一次列表，用户点对应条目可复制解决方案链接/文字。
"""
import shutil
import sys
from pathlib import Path

from paths import base_dir

PROJ = base_dir()


def _check_virtual_cable():
    """虚拟声卡（核心输出链路）。"""
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        has_cable = any(
            "cable" in (d["name"] or "").lower()
            or "vb-audio" in (d["name"] or "").lower()
            for d in devs
        )
    except Exception:
        return dict(
            id="cable", ok=False, level="error",
            title="无法查询音频设备",
            problem="读取系统音频设备列表失败。",
            solution="请尝试重启电脑后再运行本软件；如果仍失败，"
                     "请把本提示截图发给维护者。",
        )
    if has_cable:
        return dict(id="cable", ok=True, level="info", title="虚拟声卡正常",
                    problem="", solution="")
    return dict(
        id="cable", ok=False, level="error",
        title="未检测到虚拟声卡（VB-CABLE）",
        problem="软件翻译好的英文语音要通过虚拟声卡发给 Discord/游戏。"
                "没有它，对方听不到你的声音。",
        solution="安装 VB-CABLE（免费）：\n"
                 "  1. 用浏览器打开 https://vb-audio.com/Cable/ \n"
                 "  2. 下载 VB-CABLE Driver（Donation 版即可，点 0 元下载）\n"
                 "  3. 解压后右键「以管理员身份运行」VBCABLE_Setup_x64.exe\n"
                 "  4. 点 Install Driver，装完重启电脑\n"
                 "  5. 再启动本软件，本提示会自动消失",
    )


def _check_microphone():
    """有可用输入设备吗（含权限/被禁用检测）。"""
    try:
        import sounddevice as sd
        inputs = [(i, d) for i, d in enumerate(sd.query_devices())
                  if d["max_input_channels"] > 0]
    except Exception:
        inputs = []
    if not inputs:
        return dict(
            id="mic", ok=False, level="error",
            title="没有可用的录音设备",
            problem="软件需要从麦克风采集你说的中文。",
            solution="请检查：\n"
                     "  1. 麦克风/耳麦是否已插好\n"
                     "  2. 右键任务栏声音图标 → 声音设置 → 检查输入设备是否被禁用\n"
                     "  3. Windows 设置 → 隐私和安全性 → 麦克风 → "
                     "允许桌面应用访问麦克风 已打开",
        )
    # 有设备；检查系统级麦克风权限（注册表）
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager"
            r"\ConsentStore\microphone",
        )
        val, _ = winreg.QueryValueEx(key, "Value")
        winreg.CloseKey(key)
        if str(val).lower() == "deny":
            return dict(
                id="mic", ok=False, level="error",
                title="麦克风权限被系统禁用",
                problem="Windows 不允许应用使用麦克风。",
                solution="Windows 设置 → 隐私和安全性 → 麦克风 → "
                         "把「麦克风访问」打开，然后重启本软件。",
            )
    except FileNotFoundError:
        pass  # 键不存在=未设置过限制，正常
    except Exception:
        pass
    return dict(id="mic", ok=True, level="info", title="录音设备正常",
                problem="", solution="")


def _check_models():
    """模型文件齐全（打包后不应触发；开发环境防呆）。"""
    need = {
        "语音识别模型": PROJ / "models" / "moonshine-zh",
        "翻译模型": PROJ / "models" / "opus-mt-zh-en-ct2-int8",
        "翻译分词器": PROJ / "models" / "opus-mt-tokenizer",
        "语音合成模型目录": PROJ / "models" / "tinytts-onnx",
        "VAD 模型": PROJ / "models" / "silero-vad" / "silero_vad.onnx",
    }
    missing = []
    for name, p in need.items():
        if not p.exists():
            missing.append(name)
    if not missing:
        return dict(id="models", ok=True, level="info", title="模型文件齐全",
                    problem="", solution="")
    # 详细列出 TTS 的四个文件（目录在但文件缺的情况）
    tts_files = ["text_encoder.onnx", "duration_predictor.onnx",
                 "flow.onnx", "decoder.onnx"]
    if (PROJ / "models" / "tinytts-onnx").exists():
        lack = [f for f in tts_files
                if not (PROJ / "models" / "tinytts-onnx" / f).exists()]
        if lack:
            missing.append("语音合成文件：" + "、".join(lack))
    return dict(
        id="models", ok=False, level="error",
        title="模型文件缺失",
        problem="缺少：" + "；".join(missing),
        solution="软件目录不完整。请重新解压/安装完整的软件包"
                 "（models 文件夹必须完整），或联系维护者获取模型文件。",
    )


def _check_discord_hint():
    """提醒：Discord 需要手动把麦克风设为 CABLE Output（只做 warn 级提示）。"""
    try:
        import sounddevice as sd
        try:
            default_in = sd.query_devices(kind="input")["name"]
        except Exception:
            return dict(
                id="discord", ok=True, level="info",
                title="", problem="", solution="")
        has_cable_default = "cable" in default_in.lower() or \
                            "vb-audio" in default_in.lower()
        if not has_cable_default:
            return dict(
                id="discord", ok=True, level="warn",
                title="提醒：Discord 还没指向虚拟声卡",
                problem="系统默认麦克风不是 CABLE Output。",
                solution="这只是提醒，不影响本软件运行。"
                         "要在 Discord 里让对方听到英文，请设置：\n"
                         "  Discord → 用户设置 → 语音和视频 → 输入设备 →"
                         " 选「CABLE Output (VB-Audio Point)」",
            )
    except Exception:
        pass
    return dict(id="discord", ok=True, level="info", title="",
                problem="", solution="")


def run_all_checks() -> list:
    """跑全部自检。返回检查结果列表（顺序固定）。"""
    checks = [
        _check_models,
        _check_virtual_cable,
        _check_microphone,
        _check_discord_hint,
    ]
    results = []
    for fn in checks:
        try:
            results.append(fn())
        except Exception as e:
            results.append(dict(
                id="unknown", ok=False, level="warn",
                title=f"检查项 {fn.__name__} 出错",
                problem=str(e),
                solution="不影响其他功能，可忽略；如反复出现请联系维护者。",
            ))
    return results


def has_blocking_issues(results: list) -> bool:
    return any((not r["ok"]) and r["level"] == "error" for r in results)


if __name__ == "__main__":
    # 命令行直接运行本文件：打印自检报告（供排错）
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 56)
    print("启动环境自检")
    print("=" * 56)
    for r in run_all_checks():
        mark = "✓" if r["ok"] else ("⚠" if r["level"] == "warn" else "✗")
        print(f"{mark} {r['title']}")
        if not r["ok"]:
            print(f"   问题：{r['problem']}")
            print(f"   解决：{r['solution']}")
            print()
    print("=" * 56)
    print("全绿=可正常使用。✗ 必须处理，⚠ 只是提醒。")
