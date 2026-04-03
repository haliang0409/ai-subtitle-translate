"""
gui.py — AI 字幕翻译工具 图形界面
基于 customtkinter，三标签页：翻译 / API 设置 / 高级设置
"""
import os
import time
import queue
import threading
import requests
import pysubs2
import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime

import config
from translator import SubtitleTranslator, TranslationError


# ──────────────────────────────────────────────────────────
# GUITranslator — 接受直接传入的配置，无需读取环境变量
# ──────────────────────────────────────────────────────────

class GUITranslator(SubtitleTranslator):
    """SubtitleTranslator 的子类，直接接受配置字典，跳过环境变量读取。"""

    def __init__(self, api_configs: list, cfg: dict):
        # 直接设置属性，不调用 super().__init__()
        self.target_lang = cfg.get("target_language", "Chinese")
        self.max_retries = cfg.get("max_retries", 3)
        self.retry_delay = cfg.get("retry_delay", 3)
        self.request_interval = float(cfg.get("request_interval", 1.0))
        self.default_batch_size = int(cfg.get("batch_size", 30))
        self.context_window = int(cfg.get("context_window", 5))
        self.api_configs = api_configs
        self._current_api_index = 0

        if not self.api_configs:
            raise ValueError(
                "没有可用的 API 配置。\n请在「API 设置」标签页中至少添加一个 API Key。"
            )


# ──────────────────────────────────────────────────────────
# App — 主窗口
# ──────────────────────────────────────────────────────────

class App(ctk.CTk):
    FILETYPES = [
        ("字幕文件", "*.srt *.ass *.ssa *.vtt *.sub *.lrc"),
        ("所有文件", "*.*"),
    ]
    THEME_MAP = {"system": "跟随系统", "light": "浅色", "dark": "深色"}
    THEME_REV = {"跟随系统": "system", "浅色": "light", "深色": "dark"}
    CTK_THEME = {"system": "System", "light": "Light", "dark": "Dark"}

    def __init__(self):
        super().__init__()

        self._cfg = config.load()

        ctk.set_appearance_mode(self.CTK_THEME.get(self._cfg.get("theme", "system"), "System"))
        ctk.set_default_color_theme("blue")

        self.title("AI 字幕翻译工具")
        self.minsize(700, 600)
        self.geometry("800x660")

        # 翻译线程状态
        self._log_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._trans_thread: threading.Thread | None = None
        self._batch_files: list[str] = []

        # API 卡片列表
        self._api_cards: list[dict] = []

        self._build_ui()
        self.after(100, self._poll_log_queue)

    # ── UI 构建 ───────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._tabview = ctk.CTkTabview(self, anchor="nw")
        self._tabview.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        self._tabview.add("翻译")
        self._tabview.add("API 设置")
        self._tabview.add("高级设置")

        self._build_translate_tab()
        self._build_api_tab()
        self._build_advanced_tab()

    # ── 翻译 Tab ──────────────────────────────────────────

    def _build_translate_tab(self):
        tab = self._tabview.tab("翻译")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(6, weight=1)

        # 输入文件
        in_frame = ctk.CTkFrame(tab)
        in_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=(6, 2))
        in_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(in_frame, text="输入文件", width=60).grid(row=0, column=0, padx=(10, 6), pady=6)
        self._input_var = ctk.StringVar()
        inp_entry = ctk.CTkEntry(in_frame, textvariable=self._input_var, placeholder_text="选择或拖放字幕文件...")
        inp_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        inp_entry.bind("<Button-1>", lambda _: self._browse_input())
        ctk.CTkButton(in_frame, text="浏览", width=56, command=self._browse_input).grid(
            row=0, column=2, padx=(4, 10), pady=6
        )

        self._file_info_label = ctk.CTkLabel(tab, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self._file_info_label.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 2))

        # 输出文件
        out_frame = ctk.CTkFrame(tab)
        out_frame.grid(row=2, column=0, sticky="ew", padx=4, pady=2)
        out_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(out_frame, text="输出文件", width=60).grid(row=0, column=0, padx=(10, 6), pady=6)
        self._output_var = ctk.StringVar()
        ctk.CTkEntry(out_frame, textvariable=self._output_var, placeholder_text="留空则自动生成...").grid(
            row=0, column=1, sticky="ew", padx=4, pady=6
        )
        ctk.CTkButton(out_frame, text="浏览", width=56, fg_color="gray40", hover_color="gray30",
                      command=self._browse_output).grid(row=0, column=2, padx=(4, 10), pady=6)

        # 选项行
        opt_frame = ctk.CTkFrame(tab)
        opt_frame.grid(row=3, column=0, sticky="ew", padx=4, pady=2)
        ctk.CTkLabel(opt_frame, text="目标语言").pack(side="left", padx=(10, 4), pady=6)
        self._lang_var = ctk.StringVar(value=self._cfg.get("target_language", "Chinese"))
        ctk.CTkEntry(opt_frame, textvariable=self._lang_var, width=110).pack(side="left", padx=(0, 12), pady=6)
        self._resume_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(opt_frame, text="断点续传", variable=self._resume_var).pack(side="left", padx=6, pady=6)
        self._context_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opt_frame, text="增强上下文", variable=self._context_var).pack(side="left", padx=6, pady=6)

        # 批量队列
        q_frame = ctk.CTkFrame(tab)
        q_frame.grid(row=4, column=0, sticky="ew", padx=4, pady=2)
        q_frame.grid_columnconfigure(0, weight=1)
        q_hdr = ctk.CTkFrame(q_frame, fg_color="transparent")
        q_hdr.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        ctk.CTkLabel(q_hdr, text="批量队列").pack(side="left")
        ctk.CTkButton(q_hdr, text="清除", width=44, height=22, fg_color="gray40",
                      hover_color="gray30", command=self._clear_queue).pack(side="right", padx=2)
        ctk.CTkButton(q_hdr, text="添加文件", width=70, height=22,
                      command=self._add_to_queue).pack(side="right", padx=2)
        self._queue_box = ctk.CTkTextbox(q_frame, height=52, state="disabled",
                                         font=ctk.CTkFont(size=11))
        self._queue_box.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))

        # 开始/停止按钮
        self._start_btn = ctk.CTkButton(
            tab, text="▶  开始翻译", height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._toggle_translation,
        )
        self._start_btn.grid(row=5, column=0, sticky="ew", padx=4, pady=(4, 2))

        # 进度条
        prog_frame = ctk.CTkFrame(tab, fg_color="transparent")
        prog_frame.grid(row=6, column=0, sticky="ew", padx=4)
        prog_frame.grid_columnconfigure(0, weight=1)
        self._progress_bar = ctk.CTkProgressBar(prog_frame)
        self._progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=4)
        self._progress_bar.set(0)
        self._progress_label = ctk.CTkLabel(prog_frame, text="0 / 0", width=70, anchor="e")
        self._progress_label.grid(row=0, column=1, pady=4)

        # 日志框
        self._log_box = ctk.CTkTextbox(
            tab, height=150, state="disabled",
            font=ctk.CTkFont(family="Courier New", size=11),
        )
        self._log_box.grid(row=7, column=0, sticky="nsew", padx=4, pady=(2, 6))
        tab.grid_rowconfigure(7, weight=1)

    # ── API 设置 Tab ──────────────────────────────────────

    def _build_api_tab(self):
        tab = self._tabview.tab("API 设置")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self._api_scroll = ctk.CTkScrollableFrame(tab, label_text="API 配置列表（多组轮询）")
        self._api_scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 2))
        self._api_scroll.grid_columnconfigure(0, weight=1)

        # 加载已保存的 API
        for api in self._cfg.get("apis", []):
            self._add_api_card(api)

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=4, pady=(2, 6))
        ctk.CTkButton(btn_row, text="+ 添加 API", width=110,
                      command=lambda: self._add_api_card()).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="🔌 测试全部", width=110,
                      command=self._test_all_apis).pack(side="left", padx=4)

    def _add_api_card(self, api_data: dict | None = None):
        if api_data is None:
            api_data = {
                "key": "",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
                "disable_proxy": True,
            }

        idx = len(self._api_cards)
        card = ctk.CTkFrame(self._api_scroll, border_width=1)
        card.grid(row=idx, column=0, sticky="ew", padx=4, pady=4)
        card.grid_columnconfigure(1, weight=1)

        # 卡片头部
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(6, 2))
        hdr.grid_columnconfigure(0, weight=1)

        num_lbl = ctk.CTkLabel(hdr, text=f"API #{idx + 1}", font=ctk.CTkFont(weight="bold"))
        num_lbl.grid(row=0, column=0, sticky="w")
        status_var = ctk.StringVar(value="—")
        ctk.CTkLabel(hdr, textvariable=status_var, width=28).grid(row=0, column=1, padx=4)
        ctk.CTkButton(hdr, text="↑", width=28, height=24,
                      command=lambda c=card: self._move_card(c, -1)).grid(row=0, column=2, padx=2)
        ctk.CTkButton(hdr, text="↓", width=28, height=24,
                      command=lambda c=card: self._move_card(c, 1)).grid(row=0, column=3, padx=2)
        ctk.CTkButton(hdr, text="删除", width=48, height=24,
                      fg_color="#c0392b", hover_color="#e74c3c",
                      command=lambda c=card: self._remove_api_card(c)).grid(row=0, column=4, padx=(2, 0))

        # API Key
        ctk.CTkLabel(card, text="API Key", width=68, anchor="e").grid(row=1, column=0, padx=(8, 4), pady=3, sticky="e")
        key_var = ctk.StringVar(value=api_data.get("key", ""))
        ctk.CTkEntry(card, textvariable=key_var, show="•", placeholder_text="sk-...").grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=3
        )

        # Base URL
        ctk.CTkLabel(card, text="Base URL", width=68, anchor="e").grid(row=2, column=0, padx=(8, 4), pady=3, sticky="e")
        url_var = ctk.StringVar(value=api_data.get("base_url", "https://api.openai.com/v1"))
        ctk.CTkEntry(card, textvariable=url_var).grid(
            row=2, column=1, sticky="ew", padx=(0, 8), pady=3
        )

        # 模型 + 代理 + 测试
        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.grid(row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=(2, 8))

        ctk.CTkLabel(bottom, text="模型").pack(side="left", padx=(2, 4))
        model_var = ctk.StringVar(value=api_data.get("model", "gpt-4o-mini"))
        ctk.CTkEntry(bottom, textvariable=model_var, width=140).pack(side="left", padx=(0, 8))

        proxy_var = ctk.BooleanVar(value=api_data.get("disable_proxy", True))
        ctk.CTkCheckBox(bottom, text="禁用代理", variable=proxy_var).pack(side="left", padx=4)

        ctk.CTkButton(
            bottom, text="测试", width=52, height=26,
            command=lambda kv=key_var, uv=url_var, mv=model_var, pv=proxy_var, sv=status_var:
                self._test_single_api(kv, uv, mv, pv, sv),
        ).pack(side="right", padx=4)

        card_data = {
            "card": card,
            "num_lbl": num_lbl,
            "key_var": key_var,
            "url_var": url_var,
            "model_var": model_var,
            "proxy_var": proxy_var,
            "status_var": status_var,
        }
        self._api_cards.append(card_data)
        return card_data

    def _remove_api_card(self, card: ctk.CTkFrame):
        self._api_cards = [c for c in self._api_cards if c["card"] is not card]
        card.destroy()
        self._renumber_api_cards()

    def _renumber_api_cards(self):
        for i, c in enumerate(self._api_cards):
            c["card"].grid(row=i, column=0, sticky="ew", padx=4, pady=4)
            c["num_lbl"].configure(text=f"API #{i + 1}")

    def _move_card(self, card: ctk.CTkFrame, direction: int):
        idx = next((i for i, c in enumerate(self._api_cards) if c["card"] is card), None)
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._api_cards):
            return
        self._api_cards[idx], self._api_cards[new_idx] = self._api_cards[new_idx], self._api_cards[idx]
        self._renumber_api_cards()

    # ── 高级设置 Tab ──────────────────────────────────────

    def _build_advanced_tab(self):
        tab = self._tabview.tab("高级设置")
        tab.grid_columnconfigure((0, 1), weight=1)

        def slider_row(parent, row, label, var, from_, to, col=0, colspan=1):
            ctk.CTkLabel(parent, text=label, anchor="w").grid(
                row=row, column=col, columnspan=colspan, sticky="w", padx=10, pady=(8, 1)
            )
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.grid(row=row + 1, column=col, columnspan=colspan, sticky="ew", padx=10, pady=(0, 6))
            ctk.CTkSlider(f, from_=from_, to=to, variable=var, width=170).pack(side="left")
            ctk.CTkEntry(f, textvariable=var, width=55).pack(side="left", padx=6)

        def entry_row(parent, row, label, var, col=0):
            ctk.CTkLabel(parent, text=label, anchor="w").grid(
                row=row, column=col, sticky="w", padx=10, pady=(8, 1)
            )
            ctk.CTkEntry(parent, textvariable=var, width=90).grid(
                row=row + 1, column=col, sticky="w", padx=10, pady=(0, 6)
            )

        self._batch_var = ctk.IntVar(value=self._cfg.get("batch_size", 30))
        slider_row(tab, 0, "批次大小", self._batch_var, 1, 100, col=0)

        self._interval_var = ctk.DoubleVar(value=self._cfg.get("request_interval", 1.0))
        slider_row(tab, 0, "请求间隔 (秒)", self._interval_var, 0, 5, col=1)

        self._ctx_var = ctk.IntVar(value=self._cfg.get("context_window", 5))
        slider_row(tab, 2, "上下文窗口", self._ctx_var, 0, 20, col=0)

        self._retries_var = ctk.IntVar(value=self._cfg.get("max_retries", 3))
        entry_row(tab, 2, "最大重试次数", self._retries_var, col=1)

        self._retry_delay_var = ctk.IntVar(value=self._cfg.get("retry_delay", 3))
        entry_row(tab, 4, "重试间隔 (秒)", self._retry_delay_var, col=0)

        self._model_var = ctk.StringVar(value=self._cfg.get("model_name", "gpt-4o-mini"))
        entry_row(tab, 4, "默认模型", self._model_var, col=1)

        # 输出格式转换
        ctk.CTkLabel(tab, text="输出格式转换", anchor="w").grid(
            row=6, column=0, sticky="w", padx=10, pady=(8, 1)
        )
        self._out_fmt_var = ctk.StringVar(value="与输入相同")
        ctk.CTkOptionMenu(
            tab, variable=self._out_fmt_var,
            values=["与输入相同", ".srt", ".ass", ".vtt", ".lrc", ".sub"],
            width=140,
        ).grid(row=7, column=0, sticky="w", padx=10, pady=(0, 6))

        # 全局禁用代理
        self._global_proxy_var = ctk.BooleanVar(value=self._cfg.get("disable_proxy", True))
        ctk.CTkCheckBox(tab, text="全局禁用代理", variable=self._global_proxy_var).grid(
            row=7, column=1, sticky="w", padx=10, pady=(0, 6)
        )

        # 主题
        ctk.CTkLabel(tab, text="界面主题", anchor="w").grid(
            row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 1)
        )
        self._theme_var = ctk.StringVar(
            value=self.THEME_MAP.get(self._cfg.get("theme", "system"), "跟随系统")
        )
        ctk.CTkSegmentedButton(
            tab, values=["跟随系统", "浅色", "深色"],
            variable=self._theme_var,
            command=self._on_theme_change,
        ).grid(row=9, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))

        # 最近文件
        ctk.CTkLabel(tab, text="最近文件", anchor="w").grid(
            row=10, column=0, sticky="w", padx=10, pady=(8, 1)
        )
        ctk.CTkButton(tab, text="清除历史", width=80, height=24,
                      fg_color="gray40", hover_color="gray30",
                      command=self._clear_recent).grid(
            row=10, column=1, sticky="e", padx=10, pady=(8, 1)
        )
        self._recent_frame = ctk.CTkScrollableFrame(tab, height=80)
        self._recent_frame.grid(row=11, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        self._recent_frame.grid_columnconfigure(0, weight=1)
        self._refresh_recent_list()

        # 保存按钮
        ctk.CTkButton(
            tab, text="💾  保存设置", height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save_settings,
        ).grid(row=12, column=0, columnspan=2, sticky="ew", padx=10, pady=(4, 8))

    # ── 文件操作 ──────────────────────────────────────────

    def _browse_input(self):
        path = filedialog.askopenfilename(title="选择字幕文件", filetypes=self.FILETYPES)
        if path:
            self._input_var.set(path)
            self._update_file_info(path)

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="选择输出路径",
            filetypes=self.FILETYPES,
            defaultextension=".srt",
        )
        if path:
            self._output_var.set(path)

    def _update_file_info(self, path: str):
        if not path or not os.path.exists(path):
            self._file_info_label.configure(text="")
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext != ".lrc":
                subs = pysubs2.load(path)
                count = len(subs)
                self._file_info_label.configure(
                    text=f"格式：{ext.upper().lstrip('.')}  |  共 {count} 条字幕"
                )
            else:
                self._file_info_label.configure(text=f"格式：LRC 歌词文件")
        except Exception:
            self._file_info_label.configure(text=f"格式：{ext.upper().lstrip('.')}")

        # 自动生成输出路径
        if not self._output_var.get():
            base, file_ext = os.path.splitext(path)
            self._output_var.set(f"{base}_translated{file_ext}")

    def _add_to_queue(self):
        paths = filedialog.askopenfilenames(title="添加到批量队列", filetypes=self.FILETYPES)
        for p in paths:
            if p not in self._batch_files:
                self._batch_files.append(p)
        self._update_queue_display()

    def _clear_queue(self):
        self._batch_files.clear()
        self._update_queue_display()

    def _update_queue_display(self):
        self._queue_box.configure(state="normal")
        self._queue_box.delete("1.0", "end")
        for i, f in enumerate(self._batch_files):
            self._queue_box.insert("end", f"{i + 1}. {os.path.basename(f)}\n")
        self._queue_box.configure(state="disabled")

    # ── API 操作 ──────────────────────────────────────────

    def _get_api_configs(self) -> list:
        configs = []
        for i, c in enumerate(self._api_cards):
            key = c["key_var"].get().strip()
            if not key:
                continue
            configs.append({
                "key": key,
                "base_url": c["url_var"].get().strip().rstrip("/"),
                "model": c["model_var"].get().strip() or self._model_var.get().strip() or "gpt-4o-mini",
                "proxies": {"http": None, "https": None} if c["proxy_var"].get() else None,
                "label": f"API-{i + 1}",
            })
        return configs

    def _test_single_api(self, key_var, url_var, model_var, proxy_var, status_var):
        key = key_var.get().strip()
        if not key:
            messagebox.showwarning("API Key 为空", "请先填写 API Key")
            return
        status_var.set("⏳")
        t = threading.Thread(
            target=self._test_api_worker,
            args=(key, url_var.get().strip(), model_var.get().strip(),
                  proxy_var.get(), status_var),
            daemon=True,
        )
        t.start()

    def _test_all_apis(self):
        for c in self._api_cards:
            if c["key_var"].get().strip():
                self._test_single_api(
                    c["key_var"], c["url_var"], c["model_var"],
                    c["proxy_var"], c["status_var"],
                )

    def _test_api_worker(self, key: str, base_url: str, model: str,
                         disable_proxy: bool, status_var: ctk.StringVar):
        proxies = {"http": None, "https": None} if disable_proxy else None
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.7,
        }
        try:
            resp = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers, json=payload, proxies=proxies, timeout=15,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            self._log_queue.put(("api_status", status_var, "✅"))
            self._log(f"✅ [{model}] 连接成功：{content[:60]}")
        except Exception as e:
            self._log_queue.put(("api_status", status_var, "❌"))
            self._log(f"❌ [{model}] 连接失败：{e}")

    # ── 翻译控制 ─────────────────────────────────────────

    def _toggle_translation(self):
        if self._trans_thread and self._trans_thread.is_alive():
            self._stop_event.set()
            self._start_btn.configure(text="正在停止...", state="disabled")
        else:
            inp = self._input_var.get().strip()
            if not inp and not self._batch_files:
                messagebox.showwarning("未选择文件", "请先选择输入文件或添加批量队列")
                return
            self._stop_event.clear()
            self._start_btn.configure(
                text="⏹  停止翻译",
                fg_color="#c0392b", hover_color="#e74c3c",
            )
            self._progress_bar.set(0)
            self._progress_label.configure(text="0 / 0")
            self._clear_log()
            self._trans_thread = threading.Thread(target=self._run_translation, daemon=True)
            self._trans_thread.start()

    def _run_translation(self):
        api_configs = self._get_api_configs()
        cfg = self._get_current_cfg()

        try:
            translator = GUITranslator(api_configs, cfg)
        except ValueError as e:
            self._log(f"❌ {e}")
            self._log_queue.put(("done", False))
            return

        # 构建文件列表
        inp = self._input_var.get().strip()
        files: list[tuple[str, str]] = []
        if inp and os.path.exists(inp):
            out = self._output_var.get().strip()
            if not out:
                base, ext = os.path.splitext(inp)
                out = f"{base}_translated{ext}"
            files.append((inp, out))
        for f in self._batch_files:
            if os.path.exists(f):
                base, ext = os.path.splitext(f)
                files.append((f, f"{base}_translated{ext}"))

        if not files:
            self._log("⚠️ 没有有效的输入文件")
            self._log_queue.put(("done", False))
            return

        enhanced = self._context_var.get()
        resume = self._resume_var.get()
        total_files = len(files)

        for i, (inp_f, out_f) in enumerate(files):
            if self._stop_event.is_set():
                break
            self._log(f"\n{'─' * 38}")
            self._log(f"📄 [{i + 1}/{total_files}] {os.path.basename(inp_f)}")
            ext = os.path.splitext(inp_f)[1].lower()
            if ext not in translator.SUPPORTED_FORMATS:
                self._log(f"❌ 不支持的格式：{ext}，已跳过")
                continue
            translator.target_lang = self._lang_var.get().strip() or cfg["target_language"]
            self._translate_file(translator, inp_f, out_f, enhanced, resume)

        self._log_queue.put(("done", True))

    def _translate_file(self, translator: GUITranslator, input_file: str,
                        output_file: str, enhanced_context: bool, resume: bool) -> bool:
        try:
            subs = translator._load_subtitle(input_file)
        except Exception as e:
            self._log(f"❌ 无法加载文件：{e}")
            return False

        total = len(subs)
        if total == 0:
            self._log("⚠️ 文件中没有字幕条目")
            return False

        all_originals = [event.text.replace("\n", " [BR] ") for event in subs]
        all_translations: list[str | None] = [None] * total
        start_index = 0

        if resume:
            progress = translator._load_progress(output_file)
            if progress and os.path.exists(output_file):
                si = progress.get("translated_index", 0)
                if 0 < si < total:
                    try:
                        partial = translator._load_subtitle(output_file)
                        for j in range(min(si, len(partial))):
                            subs[j].text = partial[j].text
                            all_translations[j] = partial[j].text.replace("\n", " [BR] ")
                        start_index = si
                        self._log(f"📂 续上次进度：{si}/{total} 条")
                    except Exception:
                        start_index = 0

        batch_size = translator.default_batch_size
        self._update_progress(start_index, total)

        try:
            i = start_index
            while i < total:
                if self._stop_event.is_set():
                    translator._save_progress(output_file, i, subs)
                    self._log(f"⏸ 已中断，进度保存至 {i}/{total}")
                    return False

                batch_end = min(i + batch_size, total)
                batch_texts = all_originals[i:batch_end]

                if enhanced_context:
                    ctx_start = max(0, i - translator.context_window)
                    ctx_before = [
                        (all_originals[j], all_translations[j])
                        for j in range(ctx_start, i)
                        if all_translations[j]
                    ]
                    ctx_end = min(total, batch_end + translator.context_window)
                    ctx_after = all_originals[batch_end:ctx_end]
                    translated = translator.translate_batch_with_context(
                        batch_texts, ctx_before, ctx_after
                    )
                else:
                    translated = translator.translate_batch(batch_texts)

                for j, text in enumerate(translated):
                    idx = i + j
                    if idx < total:
                        final = text.replace(" [BR] ", "\n").replace("[BR]", "\n")
                        subs[idx].text = final
                        all_translations[idx] = text

                translator._save_progress(output_file, batch_end, subs)
                self._update_progress(batch_end, total)
                self._log(f"✓ {batch_end}/{total} 条完成")

                # 可中断的等待
                if batch_end < total and translator.request_interval > 0:
                    elapsed = 0.0
                    while elapsed < translator.request_interval:
                        if self._stop_event.is_set():
                            break
                        time.sleep(0.1)
                        elapsed += 0.1

                i = batch_end

        except TranslationError as e:
            self._log(f"❌ 翻译中止：{e}")
            return False

        if self._stop_event.is_set():
            return False

        # 格式转换（如有）
        out_fmt = self._out_fmt_var.get()
        final_output = output_file
        if out_fmt != "与输入相同":
            base = os.path.splitext(output_file)[0]
            final_output = base + out_fmt

        try:
            translator._clear_progress(output_file)
            if os.path.splitext(final_output)[1].lower() == ".lrc":
                translator._save_lrc(subs, final_output)
            else:
                subs.save(final_output)
            self._log(f"✅ 已保存：{final_output}")
            config.add_recent_file(input_file)
            return True
        except Exception as e:
            self._log(f"❌ 保存失败：{e}")
            return False

    # ── 日志与进度 ────────────────────────────────────────

    def _log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_queue.put(("log", f"[{ts}] {message}"))

    def _update_progress(self, current: int, total: int):
        self._log_queue.put(("progress", current, total))

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _append_log(self, text: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _poll_log_queue(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._append_log(msg[1])
                elif kind == "progress":
                    current, total = msg[1], msg[2]
                    self._progress_bar.set(current / total if total > 0 else 0)
                    self._progress_label.configure(text=f"{current} / {total}")
                elif kind == "done":
                    self._start_btn.configure(
                        text="▶  开始翻译",
                        fg_color=["#3B8ED0", "#1F6AA5"],
                        hover_color=["#36719F", "#144870"],
                        state="normal",
                    )
                    self._refresh_recent_list()
                elif kind == "api_status":
                    # msg = ("api_status", status_var, text)
                    msg[1].set(msg[2])
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    # ── 设置管理 ──────────────────────────────────────────

    def _get_current_cfg(self) -> dict:
        return {
            "target_language": self._lang_var.get().strip() or "Chinese",
            "model_name": self._model_var.get().strip(),
            "batch_size": self._batch_var.get(),
            "request_interval": round(float(self._interval_var.get()), 2),
            "context_window": self._ctx_var.get(),
            "max_retries": self._retries_var.get(),
            "retry_delay": self._retry_delay_var.get(),
            "disable_proxy": self._global_proxy_var.get(),
        }

    def _save_settings(self):
        data = config.load()

        data["apis"] = [
            {
                "key": c["key_var"].get().strip(),
                "base_url": c["url_var"].get().strip(),
                "model": c["model_var"].get().strip(),
                "disable_proxy": c["proxy_var"].get(),
            }
            for c in self._api_cards
        ]

        data.update(self._get_current_cfg())
        data["theme"] = self.THEME_REV.get(self._theme_var.get(), "system")

        config.save(data)
        messagebox.showinfo("已保存", "设置已保存到 config.json")

    def _on_theme_change(self, val: str):
        ctk.set_appearance_mode(self.CTK_THEME.get(self.THEME_REV.get(val, "system"), "System"))

    def _clear_recent(self):
        data = config.load()
        data["recent_files"] = []
        config.save(data)
        self._refresh_recent_list()

    def _refresh_recent_list(self):
        for w in self._recent_frame.winfo_children():
            w.destroy()
        recent = config.load().get("recent_files", [])
        if not recent:
            ctk.CTkLabel(self._recent_frame, text="暂无记录", text_color="gray").pack(anchor="w", padx=6)
            return
        for path in recent:
            row = ctk.CTkFrame(self._recent_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                row, text=os.path.basename(path), anchor="w",
                font=ctk.CTkFont(size=11),
            ).grid(row=0, column=0, sticky="w", padx=4)
            ctk.CTkButton(
                row, text="载入", width=42, height=22,
                command=lambda p=path: self._load_recent(p),
            ).grid(row=0, column=1, padx=4)

    def _load_recent(self, path: str):
        if os.path.exists(path):
            self._input_var.set(path)
            self._output_var.set("")
            self._update_file_info(path)
            self._tabview.set("翻译")
        else:
            messagebox.showerror("文件不存在", f"文件已移动或删除：\n{path}")
            data = config.load()
            data["recent_files"] = [f for f in data.get("recent_files", []) if f != path]
            config.save(data)
            self._refresh_recent_list()


# ──────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
