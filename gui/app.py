# -*- coding: utf-8 -*-
"""主图形界面（tkinter，无额外依赖）。

阶段8基础版 + 阶段9快捷键 + 阶段10历史 + 阶段11自检 + 阶段12后修复
+ 输入/输出麦克风选择、输入音量实时指示条（UI 优化反馈轮）。
"""
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

from audio.live_engine import LiveEngine
from audio.mic_monitor import MicLevelMonitor
from audio.output import OutputManager
from audio.pipeline import TranslationPipeline
from gui.hotkeys import HotkeyManager
from history.store import HistoryStore
from stt import create_default_stt
from translation import create_default_translator
from tts import create_default_tts

import diagnostics
import crashlog


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("实时中译英语音翻译")
        self.geometry("560x660")
        self.minsize(500, 600)

        self.engine = None
        self.loading = False
        self.ui_queue = queue.Queue()  # 引擎线程 -> UI 线程的唯一通道
        self.mic_monitor = MicLevelMonitor()

        # 全局快捷键（阶段9）：默认 Ctrl+Alt+T，可在界面改
        self.hotkeys = HotkeyManager(on_toggle=self._hotkey_toggle,
                                     default_hotkey="ctrl+alt+t")

        # 历史记录（阶段10）：存 %APPDATA%/voice-translator/history.jsonl
        self.history = HistoryStore()

        # VAD 灵敏度参数（_on_sens 会更新；启动引擎时使用）
        self._sens_params = (0.35, 6.0)

        # 底部状态栏（调试区将插在它之前）
        self._status_bar_holder = ttk.Frame(self)
        self._status_bar_holder.pack(fill="x", padx=12, pady=(2, 6), side="bottom")
        ttk.Label(self._status_bar_holder,
                  text="Discord 输入设备必须选 CABLE Output（不是你的真麦克风），否则对方听到原声",
                  foreground="#888").pack(side="left")

        self._build_ui()
        self.after(50, self._poll_ui_queue)
        self.after(80, self._poll_mic_level)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 阶段11：启动自检（后台线程跑，结果回 UI 线程弹窗——只弹有问题的）
        threading.Thread(target=self._run_diagnostics, daemon=True).start()

        # 启动时注册全局快捷键并反馈结果
        if self.hotkeys.register():
            self.hotkey_lbl.config(
                text=f"已绑定 {self.hotkeys.hotkey}（游戏中可用）", foreground="#080")
        else:
            self.hotkey_lbl.config(
                text="快捷键注册失败（可能需要管理员权限运行）", foreground="#c00")

    # ────────────────────────── UI 构建 ──────────────────────────
    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        # 状态区
        status = ttk.LabelFrame(self, text="运行状态")
        status.pack(fill="x", **pad)
        self.status_var = tk.StringVar(value="未启动")
        self.status_dot = tk.Label(status, text="●", fg="#999", font=("", 14))
        self.status_dot.pack(side="left", padx=(10, 2))
        ttk.Label(status, textvariable=self.status_var).pack(
            side="left", padx=4, pady=8)

        # 控制区
        ctrl = ttk.LabelFrame(self, text="控制")
        ctrl.pack(fill="x", **pad)
        btns = ttk.Frame(ctrl)
        btns.pack(pady=8)
        self.btn_start = ttk.Button(btns, text="▶ 开始", command=self._start)
        self.btn_start.pack(side="left", padx=6)
        self.btn_stop = ttk.Button(btns, text="■ 停止", command=self._stop,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        self.btn_history = ttk.Button(btns, text="📜 历史记录",
                                      command=self._show_history)
        self.btn_history.pack(side="left", padx=6)

        # 设置区
        sets = ttk.LabelFrame(self, text="设置")
        sets.pack(fill="x", **pad)

        # 麦克风行：输入（说话）+ 输出（翻译后从哪播出）
        row1 = ttk.Frame(sets); row1.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(row1, text="输入麦克风：").pack(side="left")
        self.mic_var = tk.StringVar()
        self.mic_box = ttk.Combobox(row1, textvariable=self.mic_var,
                                    state="readonly", width=28)
        self.mic_box.pack(side="left", padx=4)
        ttk.Button(row1, text="↻", width=3,
                   command=self._refresh_mics).pack(side="left")

        row1b = ttk.Frame(sets); row1b.pack(fill="x", padx=8, pady=2)
        ttk.Label(row1b, text="输出麦克风：").pack(side="left")
        self.out_var = tk.StringVar()
        self.out_box = ttk.Combobox(row1b, textvariable=self.out_var,
                                    state="readonly", width=28)
        self.out_box.pack(side="left", padx=4)
        ttk.Label(row1b, text="（对方听到的\"麦克风\"，默认虚拟声卡）",
                  foreground="#888").pack(side="left", padx=4)

        # 输入音量指示条
        row_lv = ttk.Frame(sets); row_lv.pack(fill="x", padx=8, pady=2)
        ttk.Label(row_lv, text="输入音量：").pack(side="left")
        self.level_bar = ttk.Progressbar(row_lv, mode="determinate",
                                         maximum=100, length=180)
        self.level_bar.pack(side="left", padx=4)
        self.level_lbl = ttk.Label(row_lv, text="0", width=4, foreground="#888")
        self.level_lbl.pack(side="left", padx=4)

        row2 = ttk.Frame(sets); row2.pack(fill="x", padx=8, pady=2)
        ttk.Label(row2, text="音量：").pack(side="left")
        self.vol_var = tk.DoubleVar(value=0.8)
        vol_scale = ttk.Scale(row2, from_=0, to=100, variable=self.vol_var,
                              command=self._on_vol)
        vol_scale.pack(side="left", fill="x", expand=True, padx=4)
        self.vol_lbl = ttk.Label(row2, text="80%", width=5)
        self.vol_lbl.pack(side="left")

        row3 = ttk.Frame(sets); row3.pack(fill="x", padx=8, pady=2)
        ttk.Label(row3, text="语速：").pack(side="left")
        self.spd_var = tk.DoubleVar(value=1.0)
        spd_scale = ttk.Scale(row3, from_=0.6, to=1.6, variable=self.spd_var,
                              command=self._on_spd)
        spd_scale.pack(side="left", fill="x", expand=True, padx=4)
        self.spd_lbl = ttk.Label(row3, text="1.00x", width=5)
        self.spd_lbl.pack(side="left")

        row3b = ttk.Frame(sets); row3b.pack(fill="x", padx=8, pady=2)
        ttk.Label(row3b, text="灵敏度：").pack(side="left")
        self.sens_var = tk.DoubleVar(value=2.0)   # 1=低 2=中(默认) 3=高
        sens_scale = ttk.Scale(row3b, from_=1, to=3, variable=self.sens_var,
                               command=self._on_sens)
        sens_scale.pack(side="left", fill="x", expand=True, padx=4)
        self.sens_lbl = ttk.Label(row3b, text="中", width=5)
        self.sens_lbl.pack(side="left")

        row4 = ttk.Frame(sets); row4.pack(fill="x", padx=8, pady=(2, 2))
        self.pb_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="本地回放（耳机里也能听到英文）",
                        variable=self.pb_var).pack(side="left")
        self.dbg_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="调试模式",
                        variable=self.dbg_var,
                        command=self._toggle_debug).pack(side="left", padx=12)

        # 快捷键设置行（阶段9）
        row5 = ttk.Frame(sets); row5.pack(fill="x", padx=8, pady=(2, 8))
        ttk.Label(row5, text="全局快捷键：").pack(side="left")
        self.hotkey_var = tk.StringVar(value=self.hotkeys.hotkey)
        hk_entry = ttk.Entry(row5, textvariable=self.hotkey_var, width=16)
        hk_entry.pack(side="left", padx=4)
        ttk.Button(row5, text="应用", width=6,
                   command=self._apply_hotkey).pack(side="left")
        self.hotkey_lbl = ttk.Label(row5, text="", foreground="#888")
        self.hotkey_lbl.pack(side="left", padx=8)

        # 调试区（默认隐藏）
        self.debug_frame = ttk.LabelFrame(self, text="调试（识别 / 翻译 / 延迟）")
        self.zh_var = tk.StringVar(value="—")
        self.en_var = tk.StringVar(value="—")
        self.lat_var = tk.StringVar(value="—")
        ttk.Label(self.debug_frame, text="识别：").grid(
            column=0, row=0, sticky="nw", padx=8, pady=2)
        ttk.Label(self.debug_frame, textvariable=self.zh_var, wraplength=430,
                  foreground="#333").grid(column=1, row=0, sticky="w")
        ttk.Label(self.debug_frame, text="翻译：").grid(
            column=0, row=1, sticky="nw", padx=8, pady=2)
        ttk.Label(self.debug_frame, textvariable=self.en_var, wraplength=430,
                  foreground="#333").grid(column=1, row=1, sticky="w")
        ttk.Label(self.debug_frame, text="延迟：").grid(
            column=0, row=2, sticky="nw", padx=8, pady=2)
        ttk.Label(self.debug_frame, textvariable=self.lat_var,
                  foreground="#080").grid(column=1, row=2, sticky="w")

        self._refresh_mics(first=True)

    # ────────────────────────── 设备列表 ─────────────────────
    def _refresh_device_maps(self):
        """重新枚举输入设备，更新名字→编号映射（不动 UI 下拉框）。
        每次点【开始】前调用：RDP 重连/插拔设备会让编号漂移，
        按名字重新解析才不会用到过期编号。

        另做一层同名去重：Windows 会把同一块物理设备在多个 Host API
        （MME / DirectSound / WASAPI / WDM-KS）下各列一条【同名】设备。
        若直接按名字建映射，后者会覆盖前者——而 WDM-KS 排在枚举最后，
        它是裸内核流，只认硬件原生采样率/位宽（Realtek 麦阵列在它
        下面怎么开都报 Invalid sample rate -9997）。这里同名只保留
        最容易打开的变体：WASAPI（共享模式，系统自动重采样）优先。
        """
        import sounddevice as sd
        try:
            devs = sd.query_devices()
            pref_by_api = {"windows wasapi": 0, "mme": 1,
                           "windows directsound": 2, "windows wdm-ks": 3}
            best = {}    # 名字 -> (优先级, 设备号)
            order = []   # 首次出现顺序（下拉框显示用，同名只显示一条）
            for i, d in enumerate(devs):
                if d["max_input_channels"] <= 0:
                    continue
                name = d["name"]
                api = sd.query_hostapis(d["hostapi"])["name"].lower()
                pref = pref_by_api.get(api, 1)
                if name not in best:
                    order.append(name)
                    best[name] = (pref, i)
                elif pref < best[name][0]:
                    best[name] = (pref, i)
            inputs = [(best[name][1], name) for name in order]
        except Exception:
            inputs = []
        self._mic_map = {name: i for i, name in inputs}
        self._out_map = dict(self._mic_map)
        return inputs

    def _refresh_mics(self, first=False):
        import sounddevice as sd
        inputs = self._refresh_device_maps()
        # 不做任何设备校验/探测——探测本身要试开每个设备，既慢又可能
        # 干扰敏感驱动；设备能不能用只有真正启动时才知道，交给
        # LiveEngine 的多参数回退 + 人话报错处理。
        in_names = []
        default_in_idx = 0
        try:
            default_in = sd.query_devices(kind="input")["name"]
        except Exception:
            default_in = None
        for i, name in inputs:
            in_names.append(name)
            if name == default_in:
                default_in_idx = len(in_names) - 1
        self.mic_box["values"] = in_names
        if in_names:
            # 保留用户已选的设备（按名字在新列表里找）；
            # 只有首次构建（还没选过）或已选设备消失时才用系统默认
            current = self.mic_var.get()
            if current and current in in_names:
                self.mic_var.set(current)
            else:
                self.mic_var.set(in_names[default_in_idx])
        # 输出麦克风下拉框：也是输入类设备——英文语音"伪装"成哪个麦克风。
        # 默认选虚拟声卡（CABLE Output / VB-Audio），Discord 从这里收到英文。
        out_names = []
        default_out_idx = 0
        for i, name in inputs:
            out_names.append(name)
            nl = name.lower()
            if ("cable" in nl or "vb-audio" in nl) and "output" in nl \
                    and default_out_idx == 0:
                default_out_idx = len(out_names) - 1
        self.out_box["values"] = out_names
        if out_names:
            # 同样保留用户已选的输出麦克风；只有没选过/已消失才回落默认
            cur_out = self.out_var.get()
            if cur_out and cur_out in out_names:
                self.out_var.set(cur_out)
            else:
                self.out_var.set(out_names[default_out_idx])
        if first and not inputs:
            self._set_status("未检测到输入设备", "red")

    # ────────────────────────── 输入音量指示 ──────────────────
    def _poll_mic_level(self):
        """80ms 轮询一次电平：未启动时用独立监视流；运行中用引擎采集。"""
        try:
            if self.engine is not None:
                # 引擎运行中：从引擎最近的采集块拿电平
                lvl = self.engine.last_input_level
                self.mic_monitor.stop()
            else:
                # 未启动：若输入设备变了则重开监视流
                dev = self._mic_map.get(self.mic_var.get())
                self.mic_monitor.maybe_restart(dev)
                self.mic_monitor.decay(0.72)
                lvl = self.mic_monitor.level
            pct = min(100, int(lvl * 400))   # RMS 0.25 即满格
            self.level_bar["value"] = pct
            self.level_lbl.config(text=str(pct))
            # 满格附近提示爆音（红色）
            self.level_lbl.config(foreground="#c00" if pct > 92 else "#888")
        except Exception:
            pass
        self.after(80, self._poll_mic_level)

    # ────────────────────────── 启停 ────────────────────────────
    VIRTUAL_MIC_KEYWORDS = ("cable", "vb-audio", "virtual", "voicemeeter",
                            "stereo mix", "virtual-audio")

    @classmethod
    def _is_virtual_mic(cls, name: str) -> bool:
        """按设备名特征判断是否虚拟麦克风（虚拟声卡软件会带这些字样）。"""
        nl = (name or "").lower()
        return any(k in nl for k in cls.VIRTUAL_MIC_KEYWORDS)

    def _start(self):
        if self.engine is not None or self.loading:
            return
        # 先重新枚举设备：RDP 重连/插拔麦克风会使设备编号变化，
        # 启动时缓存的编号可能已过期（表现为"选自己的麦克风打不开，
        # 点一下刷新又好了"）。按【名字】重新解析最新编号。
        self._refresh_device_maps()
        mic_name = self.mic_var.get().split("  [")[0]  # 剥掉可用性标注
        if not mic_name or mic_name not in self._mic_map:
            self._set_status("请先选择输入麦克风", "red")
            return
        # 输入麦克风不做任何拦截：用户选什么就试什么，
        # 打不开时 LiveEngine 会给出人话错误（含设备名和排查建议）
        # 提醒（不拦截）：输入选了虚拟声卡 → 它收不到你说话的人声，
        # 只会录到虚拟声卡线路里的声音。特别是：输出麦克风也是虚拟声卡时，
        # 我们播的 TTS 英文会被输入录回来再送去识别→翻译，形成回声循环。
        if self._is_virtual_mic(mic_name):
            go_on = messagebox.askyesno(
                "提示：虚拟麦克风不收人声",
                f"「{mic_name}」是虚拟声卡，它收不到你对着麦克风说的话。\n"
                "它只会录到电脑线路里的声音——包括本软件自己播放的英文，\n"
                "那样会造成\"自己听自己\"的循环，翻译结果会错乱。\n\n"
                "正常使用请选你的真实麦克风（耳机麦/USB麦等）；\n"
                "Discord 的输入设备保持选 CABLE Output（收英文）。\n\n"
                "仍要用它启动吗？（仅调试线路声音时才需要）",
                parent=self)
            if not go_on:
                self._set_status("已取消（请选择真实麦克风）", "#b80")
                return
        # 校验：输出麦克风必须是虚拟麦克风（英文要"伪装"成它发给对方；
        # 选成实体麦克风会导致对方听到原声/软件输出互相干扰）
        out_name = self.out_var.get()
        if out_name and not self._is_virtual_mic(out_name):
            self._set_status("输出麦克风必须是虚拟声卡", "red")
            messagebox.showwarning(
                "输出麦克风不正确",
                f"「{out_name}」不是虚拟麦克风。\n\n"
                "翻译后的英文需要通过虚拟声卡（VB-CABLE）发给 Discord/游戏。\n"
                "请在「输出麦克风」下拉框中选择带 CABLE / VB-Audio 字样的设备，"
                "然后重新点开始。",
                parent=self)
            return
        dev = self._mic_map[mic_name]
        out_dev = self._out_map.get(self.out_var.get())  # 可能为 None（用默认）
        self.loading = True
        self._set_status("模型加载中……（首次约 5 秒）", "#b80")
        self.btn_start["state"] = "disabled"
        self.mic_monitor.stop()   # 引擎要占用输入设备

        def worker():
            try:
                pipe = TranslationPipeline(
                    stt=create_default_stt(),
                    translator=create_default_translator(),
                    tts=create_default_tts(),
                    debug=True, debug_print=lambda m: None,
                )
                load_t = pipe.load_all()
                out = OutputManager(volume=self.vol_var.get() / 100.0,
                                    local_playback=self.pb_var.get(),
                                    output_device=out_dev)
                eng = LiveEngine(
                    pipe, out, input_device=dev,
                    debug=False,
                    on_event=self._on_engine_event,
                    history=self.history,
                    vad_threshold=self._sens_params[0],
                )
                eng.set_sensitivity(self._sens_params[0], self._sens_params[1])
                eng.set_speed(self.spd_var.get())
                eng.start()
                self.engine = eng
                # 麦克风没打开也照常启动（不阻塞）——只把事实带给界面
                self.ui_queue.put(("started", (load_t,
                                               eng._mic_open_failed,
                                               eng._mic_open_error)))
            except Exception as e:
                err = "".join(traceback.format_exception_only(e)).strip()
                self.ui_queue.put(("start_failed", err))

        threading.Thread(target=worker, daemon=True).start()

    def _stop(self):
        if self.engine is None:
            return
        try:
            self.engine.stop()
        finally:
            self.engine = None
        self._set_status("已停止", "#999")
        self.btn_start["state"] = "normal"
        self.btn_stop["state"] = "disabled"
        self.status_dot["fg"] = "#999"
        # 重启电平监视（设备已释放；同样按名字重新解析最新编号）
        def _restart_monitor():
            self._refresh_device_maps()
            name = self.mic_var.get().split("  [")[0]
            self.mic_monitor.start(self._mic_map.get(name))
        threading.Thread(target=_restart_monitor, daemon=True).start()

    # ────────────────────────── 引擎事件 ─────────────────────────
    def _on_engine_event(self, ev):
        # 引擎线程里调用：只入队，不碰 UI
        self.ui_queue.put(("event", ev))

    def _poll_ui_queue(self):
        try:
            while True:
                kind, data = self.ui_queue.get_nowait()
                if kind == "started":
                    load_t, mic_failed, mic_err = data
                    if mic_failed:
                        # 启动照常，只是收不到声音——如实告知一句
                        self._set_status(
                            f"已启动（麦克风「{self.mic_var.get()}」没能打开："
                            f"{mic_err}）", "#b80")
                    else:
                        self._set_status("正在监听……（说中文，停顿后出英文）", "#080")
                    self.btn_start["state"] = "disabled"
                    self.btn_stop["state"] = "normal"
                    self.status_dot["fg"] = "#0c0" if not mic_failed else "#fa0"
                    self.loading = False
                elif kind == "start_failed":
                    self._set_status(f"启动失败：{data}", "red")
                    self.btn_start["state"] = "normal"
                    self.loading = False
                elif kind == "event":
                    self._handle_event(data)
                elif kind == "hotkey_toggle":
                    self._do_hotkey_toggle()
                elif kind == "diag":
                    self._show_diagnostics(data)
        except queue.Empty:
            pass
        self.after(50, self._poll_ui_queue)

    def _handle_event(self, ev):
        if not self.dbg_var.get():
            return
        if ev.get("ok"):
            self.zh_var.set(ev.get("zh", ""))
            self.en_var.set(ev.get("en", ""))
            d = ev.get("first_audio_delay_ms")
            st = ev.get("stages_ms", {})
            seg_s = ev.get("seg_dur", 0)
            extra = " ".join(f"{k}{v:.0f}ms" for k, v in st.items())
            self.lat_var.set(
                f"{d:.0f} ms  (段落{seg_s:.1f}s | {extra})" if d else "—"
            )
        else:
            self.zh_var.set(f"失败：{ev.get('error', '')}")

    # ────────────────────────── 设置回调 ─────────────────────────
    def _on_vol(self, _):
        # ttk.Scale 的 command 回调传的是字符串；读 DoubleVar 保证类型正确
        v = float(self.vol_var.get())
        self.vol_lbl["text"] = f"{v:.0f}%"
        if self.engine:
            self.engine.set_volume(v / 100.0)

    def _on_spd(self, _):
        v = float(self.spd_var.get())
        self.spd_lbl["text"] = f"{v:.2f}x"
        if self.engine:
            self.engine.set_speed(v)

    def _on_sens(self, _):
        v = float(self.sens_var.get())
        mapping = {
            1: (0.5, 3.0, "低"), 2: (0.35, 6.0, "中"), 3: (0.22, 10.0, "高"),
        }
        key = min(mapping, key=lambda k: abs(k - v))
        thr, gain, label = mapping[key]
        self.sens_lbl["text"] = label
        self._sens_params = (thr, gain)
        if self.engine:
            self.engine.set_sensitivity(thr, gain)

    def _toggle_debug(self):
        if self.dbg_var.get():
            self.debug_frame.pack(fill="x", padx=12, pady=4,
                                  before=self._status_bar_holder)
        else:
            self.debug_frame.pack_forget()

    # ────────────────────────── 历史记录（阶段10） ────────────────
    def _show_history(self):
        win = tk.Toplevel(self)
        win.title("翻译历史记录")
        win.geometry("640x420")
        win.transient(self)

        top = ttk.Frame(win)
        top.pack(fill="x", padx=8, pady=(8, 2))
        count = self.history.count()
        ttk.Label(top, text=f"共 {count} 条（最新在前）").pack(side="left")
        ttk.Button(top, text="↻ 刷新", command=lambda: self._fill_history(tree)
                   ).pack(side="left", padx=8)
        ttk.Button(top, text="清空全部",
                   command=lambda: self._clear_history(tree, count_lbl)
                   ).pack(side="right")
        count_lbl = ttk.Label(top, text="")
        count_lbl.pack(side="right", padx=8)

        cols = ("time", "zh", "en")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        tree.heading("time", text="时间")
        tree.heading("zh", text="中文（你说的）")
        tree.heading("en", text="英文（对方听到的）")
        tree.column("time", width=130, anchor="w")
        tree.column("zh", width=210, anchor="w")
        tree.column("en", width=260, anchor="w")

        ysb = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ysb.set)
        tree.pack(fill="both", expand=True, padx=8, pady=(2, 4))
        ysb.pack(fill="y", side="right", padx=(0, 8), pady=(2, 4))

        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bottom, text="导出为文本",
                   command=lambda: self._export_history(win)).pack(side="left")
        tip = ttk.Label(bottom, text="双击一行可复制英文",
                        foreground="#888")
        tip.pack(side="right")

        def on_dbl(_e):
            sel = tree.selection()
            if sel:
                vals = tree.item(sel[0], "values")
                if len(vals) >= 3:
                    self.clipboard_clear()
                    self.clipboard_append(vals[2])
                    count_lbl.config(text="已复制英文到剪贴板")

        tree.bind("<Double-1>", on_dbl)
        self._fill_history(tree)

    def _fill_history(self, tree):
        for iid in tree.get_children():
            tree.delete(iid)
        for rec in self.history.get_recent(limit=500):
            tree.insert("", "end", values=(
                rec.get("time", ""),
                rec.get("zh", ""),
                rec.get("en", ""),
            ))

    def _clear_history(self, tree, count_lbl):
        if messagebox.askyesno(
                "确认", "确定清空全部历史记录吗？此操作不可恢复。",
                parent=self):
            self.history.clear()
            self._fill_history(tree)
            count_lbl.config(text="已清空")

    def _export_history(self, win):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            parent=win,
            defaultextension=".txt",
            initialfile=f"翻译历史_{time.strftime('%Y%m%d_%H%M%S')}.txt",
            filetypes=[("文本文件", "*.txt")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for rec in self.history.get_recent(limit=100000):
                    f.write(f"[{rec.get('time', '')}]\n"
                            f"中：{rec.get('zh', '')}\n"
                            f"英：{rec.get('en', '')}\n\n")
            messagebox.showinfo("完成", f"已导出到：\n{path}", parent=win)
        except Exception as e:
            messagebox.showerror("失败", f"导出失败：{e}", parent=win)

    # ────────────────────────── 启动自检（阶段11） ────────────────
    def _run_diagnostics(self):
        try:
            results = diagnostics.run_all_checks()
        except Exception:
            return
        self.ui_queue.put(("diag", results))

    def _show_diagnostics(self, results):
        """有 error/warn 时弹一次汇总窗；全通过则不打扰。"""
        issues = [r for r in results
                  if (not r["ok"]) or r["level"] == "warn"]
        if not issues:
            return

        win = tk.Toplevel(self)
        win.title("启动检查")
        win.geometry("620x440")
        win.transient(self)

        header = ("发现 "
                  f"{sum(1 for r in issues if r['level']=='error')} 个必须处理、"
                  f"{sum(1 for r in issues if r['level']=='warn')} 个提醒"
                  "\n（处理完成后重启软件，本提示自动消失）")
        ttk.Label(win, text=header, padding=8,
                  foreground="#a30").pack(fill="x")

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=8, pady=4)

        for r in issues:
            box = ttk.LabelFrame(body, text=r["title"])
            box.pack(fill="x", pady=4, anchor="n")
            level_color = "#c00" if r["level"] == "error" else "#a60"
            ttk.Label(box, text="●" + ("必须处理" if r["level"] == "error"
                                       else "提醒"),
                      foreground=level_color).pack(
                side="left", padx=(8, 4), pady=8, anchor="n")
            text_frame = ttk.Frame(box)
            text_frame.pack(side="left", fill="both", expand=True, pady=4)
            ttk.Label(text_frame, text=r["problem"], wraplength=470,
                      foreground="#333").pack(anchor="w")
            ttk.Label(text_frame, text="—", foreground="#bbb").pack(anchor="w")
            ttk.Label(text_frame, text=r["solution"], wraplength=470,
                      foreground="#06a").pack(anchor="w")

        ttk.Button(win, text="我知道了", command=win.destroy).pack(pady=8)

    # ────────────────────────── 快捷键（阶段9） ──────────────────
    def _hotkey_toggle(self):
        # keyboard 库的回调线程里执行；转投 UI 线程
        self.ui_queue.put(("hotkey_toggle", None))

    def _apply_hotkey(self):
        combo = self.hotkey_var.get().strip().lower()
        if not combo:
            self.hotkey_lbl.config(text="请输入组合键，如 ctrl+alt+t",
                                    foreground="#c00")
            return
        ok = self.hotkeys.set_hotkey(combo)
        if ok:
            self.hotkey_lbl.config(text=f"已绑定 {combo}", foreground="#080")
        else:
            self.hotkey_lbl.config(text="绑定失败，检查格式（如 ctrl+alt+t）",
                                    foreground="#c00")

    def _do_hotkey_toggle(self):
        # UI 线程里真正执行开关
        if self.engine is not None:
            self._stop()
        elif not self.loading:
            self._start()

    # ────────────────────────── 状态栏 ───────────────────────────
    def _set_status(self, text, color="#333"):
        self.status_var.set(text)
        try:
            self.status_dot["fg"] = {"red": "#c00", "#999": "#999"}.get(color, color)
        except Exception:
            pass

    def _on_close(self):
        self.hotkeys.close()
        self.mic_monitor.stop()
        self._stop()
        self.destroy()


def main():
    # 崩溃日志：任何未捕获异常/原生崩溃都写 %APPDATA%/voice-translator/crash.log
    # （"莫名闪退"不再莫名——事后有栈可查）
    try:
        crashlog.install()
    except Exception:
        pass

    # --selftest：打包验收专用——无界面跑完三模型加载+全链路合成，成功退出码 0
    if "--selftest" in sys.argv:
        log_path = Path("selftest_result.txt").resolve()
        log = []
        def P(msg):
            log.append(str(msg))
        try:
            import numpy as np
            P("[selftest] 加载 STT / 翻译 / TTS / VAD ……")
            stt = create_default_stt(); stt.load()
            translator = create_default_translator(); translator.load()
            tts = create_default_tts(); tts.load()
            from vad import create_default_vad
            vad = create_default_vad(); vad.load()
            P("[selftest] 三模型+VAD 加载成功")
            zh = "今天天气真好"
            en = translator.translate(zh)
            P(f"[selftest] 翻译: {zh} -> {en}")
            audio, sr = tts.synthesize(en)
            P(f"[selftest] TTS 合成: {len(audio)/sr:.2f}s @ {sr}Hz")
            frame = np.zeros(512, dtype=np.float32)
            p = vad.is_speech(frame)
            P(f"[selftest] VAD 帧检测 OK (p={p:.2f})")
            P("[selftest] 全部通过")
            log_path.write_text("\n".join(log), encoding="utf-8")
            sys.exit(0)
        except Exception as e:
            P(f"[selftest] 失败: {e}")
            log_path.write_text("\n".join(log), encoding="utf-8")
            sys.exit(1)

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
