# -*- coding: utf-8 -*-
"""Piper 中文 TTS 前端（拼音音素化，g2pW ONNX 免 torch 版）。

来源：OHF-Voice/piper1-gpl（Apache License 2.0）
  - phonemize_chinese.py 部分由 ChatGPT 撰写（2025-12）
  - g2pw_onnx.py 移植自 GitYCC/g2pW（Apache-2.0）
仅做最小改动以适配本项目（去掉与推理无关的日志依赖等）。
"""
