# -*- coding: utf-8 -*-
"""阶段1 工具：列出本机所有音频设备，帮助找到麦克风和虚拟声卡的名字。"""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import sounddevice as sd

print("=" * 60)
print("本机音频设备列表")
print("=" * 60)
try:
    default_in = sd.query_devices(kind="input")
    print(f"默认输入设备：{default_in['name']}")
except Exception:
    print("默认输入设备：（系统未设置，或没有可用输入设备）")
try:
    default_out = sd.query_devices(kind="output")
    print(f"默认输出设备：{default_out['name']}")
except Exception:
    print("默认输出设备：（系统未设置，或没有可用输出设备）")
print()

devices = sd.query_devices()

print("【输入设备】—— 你的麦克风会显示在这里；装好VB-CABLE后，CABLE Output 也会出现在这里")
found_input = False
for i, d in enumerate(devices):
    if d["max_input_channels"] > 0:
        found_input = True
        print(f"  输入#{i}: {d['name']}  (最大声道数 {d['max_input_channels']})")

print()
print("【输出设备】—— 扬声器/耳机会显示在这里；装好VB-CABLE后，CABLE Input 会出现在这里")
found_output = False
for i, d in enumerate(devices):
    if d["max_output_channels"] > 0:
        found_output = True
        print(f"  输出#{i}: {d['name']}  (最大声道数 {d['max_output_channels']})")

print()
if not found_input:
    print("⚠ 没有检测到任何输入设备！请检查麦克风是否插好/已启用。")
if not found_output:
    print("⚠ 没有检测到任何输出设备！")
names = " ".join(d["name"] for d in devices)
if "CABLE" not in names.upper():
    print("⚠ 列表里没有 CABLE 设备 —— 还没安装 VB-CABLE 虚拟声卡，")
    print("  请按 Claude Code 给出的步骤安装后重新运行本脚本。")
else:
    print("✓ 检测到 CABLE 设备，虚拟声卡已安装。")
