# VoiceTranslator — 实时中译英语音翻译

**对麦克风说中文，对方在语音里听到英文。** 全程本地 CPU 推理，无任何云端 API，
专为 Discord / 游戏语音设计：翻译后的英文通过虚拟声卡"伪装"成你的麦克风发出去。

> 典型场景：和外国队友开黑打游戏。你说"左转有人在蹲"，队友听到 "Turn left,
> someone is camping at the door." —— 延迟约 1.5 秒，中文说完停顿一下即出英文。

## 功能特性

- 🎙️ **实时翻译**：说一句中文，停顿后自动翻译成英文语音发出（VAD 自动断句）
- 🔊 **虚拟麦克风输出**：英文语音写入 VB-CABLE 虚拟声卡，Discord/游戏把它当"你的麦克风"
- 💻 **纯本地运行**：识别 / 翻译 / 合成全部在本机 CPU 完成，不联网、不上传、无 API 费用
- 🖱️ **开箱即用**：图形界面，输入/输出设备自由选择，全局快捷键一键开关
- 📜 **历史记录**：每句翻译自动存档，可导出文本
- ⚙️ **可调**：音量 / 语速 / 灵敏度 / 快捷键 / 本地回放（耳机同时听英文）

## 工作原理

```
 麦克风 ──► Silero VAD 断句 ──► Moonshine 中文识别 ──► opus-mt 中译英
                                                          │
 你说中文                                                  ▼
                                              TinyTTS 合成英文语音
                                                          │
 Discord/游戏 ◄── "CABLE Output"（虚拟麦克风）◄── 写入 VB-CABLE 虚拟声卡
```

| 环节 | 模型 | 大小 | 许可 |
|---|---|---|---|
| 语音识别 (STT) | [Moonshine tiny-streaming-zh](https://github.com/moonshine-ai/moonshine) | 31MB | MIT |
| 翻译 (MT) | [opus-mt-zh-en](https://huggingface.co/Helsinki-NLP/opus-mt-zh-en) → CTranslate2 int8 | 78MB | CC-BY-4.0 |
| 语音合成 (TTS) | [TinyTTS](https://github.com/tronghieuit/tiny-tts) ONNX | 32MB | Apache-2.0 |
| 断句 (VAD) | [Silero VAD](https://github.com/snakers4/silero-vad) | 2.2MB | MIT |

四个模块全部走 ONNX/CTranslate2 推理，**不依赖 PyTorch**，4 核老 CPU 也能实时跑。

## 快速开始

### 0. 前置要求

- Windows 10/11（需 x64）
- Python 3.10–3.12
- [VB-CABLE 虚拟声卡](https://vb-audio.com/Cable/)（免费，装完重启一次系统）

### 1. 安装

```bat
git clone https://github.com/<你的用户名>/voice-translator.git
cd voice-translator

:: 建虚拟环境 + 装依赖
python -m venv venv
venv\Scripts\pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### 2. 下载模型（约 146MB，一键脚本，国内自动走镜像）

```bat
scripts\下载模型.bat
```

### 3. 运行

```bat
scripts\8-图形界面.bat
```

界面里选好**输入麦克风**（你说话用的）和**输出麦克风**（默认虚拟声卡），点 ▶ 开始。
**Discord 设置里把输入设备换成 `CABLE Output`**——大功告成。

> 💡 使用技巧：说完一句中文**停顿约半秒**即触发翻译；灵敏度滑块调 VAD 触发
> 阈值（说话小声就往"高"调）；快捷键默认 `Ctrl+Alt+T` 游戏内可直接开关。

## 使用手册 / 开发文档

- [docs/使用手册.md](docs/使用手册.md) —— 面向使用者：设备怎么选、常见问题、Discord 配置图解
- [docs/开发文档.md](docs/开发文档.md) —— 面向开发者：架构、目录、打包、压测、踩坑记录

## 目录结构

```
voice-translator/
├── audio/            采集/输出/流水线/实时引擎
│   ├── mic_monitor.py     输入音量监视（UI 电平条）
│   ├── output.py          虚拟声卡输出管理
│   ├── pipeline.py        STT→MT→TTS 编排
│   └── live_engine.py     实时引擎（采集→VAD→处理→播放）
├── stt/              语音识别（Moonshine ONNX）
├── translation/      翻译（opus-mt → CTranslate2 int8）
├── tts/              语音合成（TinyTTS ONNX + 轻量英文文本前端）
├── vad/              断句（Silero VAD ONNX）
├── gui/              tkinter 图形界面 + 全局快捷键
├── history/          翻译历史（JSONL 存储）
├── scripts/          各阶段测试脚本 + 一键下载模型 + 压力测试
├── third_party/      TinyTTS 文本前端（CMU 词典等第三方数据）
├── crashlog.py       崩溃日志（闪退后到 %APPDATA% 留栈）
├── diagnostics.py    启动自检（模型/声卡/麦克风权限）
└── paths.py          源码/打包统一路径解析
```

## 常见问题（详见使用手册）

- **对方听到中文原声而不是英文？** Discord 输入设备没选 `CABLE Output`，还在用你的真麦克风。
- **说话没反应？** 看界面"输入音量"条有没有跳动；没有就是设备选错或灵敏度太低。
- **翻译延迟高？** 本机性能差时属正常（见下表）；确保关闭其他吃 CPU 的程序。

## 性能参考（4 核 1.88GHz 老 CPU）

| 环节 | 耗时 |
|---|---|
| 识别 STT（5s 语音） | ~0.3s |
| 翻译 MT | ~0.2s |
| 合成 TTS（10 词） | ~1.0s |
| **端到端（说完→英文开播）** | **≈1.5s** |

## 许可证

本项目代码以 [CC-BY-NC-4.0](LICENSE) 提供：**非商业使用完全自由**（使用、修改、
分发均可，需署名）；**商业使用需另行授权**。所依赖的开源模型许可见上表，
各组件的署名与许可全文见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

> 本软件永久免费，不接受任何形式的收费分发。

## 致谢

- 本项目由 **awafeng** 发起并主导开发
- 感谢 **GLM** 与 **Claude Code** 参与部分代码与文档的开发工作
- 感谢 Moonshine AI、Helsinki-NLP、TinyTTS、Silero 的开源模型（见上方许可证表格）
