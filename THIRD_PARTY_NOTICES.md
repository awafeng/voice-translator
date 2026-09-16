# 第三方组件声明（Third Party Notices）

本项目集成了以下开源模型与数据。各组件依其自身许可分发，本节为署名与许可说明。

---

## 1. Moonshine（语音识别模型 tiny-streaming-zh + moonshine_voice 库）

- 来源：<https://github.com/moonshine-ai/moonshine>
- 版权：Copyright (c) 2025 Moonshine AI / Useful Sensors, Inc.
- 许可：**MIT License**（tiny-streaming-zh 属流式模型，按官方 LICENSE 全部流式
  模型均为 MIT；非 MIT 的仅限老版非流式非英语模型，本项目未使用）

```
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 2. opus-mt-zh-en（中英翻译模型，CTranslate2 int8 转换版）

- 来源：<https://huggingface.co/Helsinki-NLP/opus-mt-zh-en>
- 版权：Helsinki-NLP（OPUS-MT 项目，University of Helsinki）
- 许可：**CC-BY-4.0**（要求署名——本文件即为署名）

> 注：仓库 `models/opus-mt-zh-en-ct2-int8/` 是原模型的 CTranslate2 int8
> 量化转换版（转换工具 CTranslate2，Apache-2.0），模型权重内容未做任何修改。

## 3. TinyTTS（英文语音合成模型 + 文本前端参考代码）

- 来源：<https://github.com/tronghieuit/tiny-tts>
- 许可：**Apache License 2.0**
- 说明：`models/tinytts-onnx/` 为官方 4 件套 ONNX 导出；
  `third_party/tiny_tts_text/` 中的 `symbols.py`、`english.py`、
  `english_utils/` 取自官方仓库（本项目以无 torch 的轻量实现复刻了其
  `english.py` 前端逻辑，见 `tts/text_frontend.py`）。

Apache License 2.0 全文见 <https://www.apache.org/licenses/LICENSE-2.0>。

## 4. Silero VAD（语音活动检测模型）

- 来源：<https://github.com/snakers4/silero-vad>
- 版权：Silero Team
- 许可：**MIT License**（`models/silero-vad/silero_vad.onnx` 取自
  onnx-community 镜像，同许可）

## 5. CMU Pronouncing Dictionary（cmudict）

- 来源：<http://www.speech.cs.cmu.edu/cgi-bin/cmudict>
- 版权：Copyright 1998 Carnegie Mellon University
- 许可：官方声明"Use of this dictionary, for any research or commercial
  purpose, is completely unrestricted"，要求再分发时注明来源——本文件即注明。
- 位置：`third_party/tiny_tts_text/cmudict.rep`（TinyTTS 文本前端发音词典）

## 6. 运行时依赖（pip 包）

| 包 | 许可 | 用途 |
|---|---|---|
| sounddevice / soundfile | MIT / BSD-3 | 音频采集与播放 |
| ctranslate2 | MIT | 翻译推理 |
| sentencepiece | Apache-2.0 | 翻译分词 |
| onnxruntime | MIT | ONNX 推理 |
| numpy | BSD-3 | 数值计算 |
| moonshine-voice | MIT | STT 模型运行时（含 moonshine.dll） |
| keyboard | MIT | 全局快捷键 |
| PyInstaller（打包用） | GPL-2.0 with bootloader exception | 仅构建期使用，运行时不依赖，不影响本仓库许可 |

---

**汇总**：本项目（代码）以 CC-BY-NC-4.0 提供；上述第三方组件依各自许可
（MIT / Apache-2.0 / CC-BY-4.0 / CMU 无限制声明）分发。若你需要**商用**本软件，
除取得本项目商业授权外，上述 MIT/Apache 组件本身允许商用，CC-BY-4.0
（opus-mt 模型）亦允许商用（需署名）。
