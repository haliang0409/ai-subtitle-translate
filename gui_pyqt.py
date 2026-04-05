import os
import sys
import time
import queue
import threading
import requests
import pysubs2
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit,
    QProgressBar, QFrame, QScrollArea, QComboBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QSlider, QMessageBox, QListWidget, QListWidgetItem,
    QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, QSize
from PyQt6.QtGui import QFont, QIcon

import config
from translator import SubtitleTranslator, TranslationError

MODERN_STYLE = """
/* Modern UI PyQt6 Stylesheet */
QMainWindow { background-color: #f8f9fa; }

QWidget {
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px; 
    color: #212529;
}

QTabWidget::pane { 
    border: 1px solid #dee2e6; 
    background: #ffffff; 
    border-radius: 8px; 
}

QTabBar::tab {
    background: #e9ecef; 
    color: #495057; 
    padding: 12px 24px; 
    margin-right: 4px;
    border-top-left-radius: 8px; 
    border-top-right-radius: 8px; 
    font-weight: 600;
}

QTabBar::tab:selected {
    background: #ffffff; 
    color: #0d6efd; 
    border: 1px solid #dee2e6; 
    border-bottom: none;
}

QTabBar::tab:hover:!selected { 
    background: #dee2e6; 
}

QPushButton {
    background-color: #0d6efd; 
    color: white; 
    border: none; 
    padding: 8px 16px;
    border-radius: 6px; 
    font-weight: 600;
}

QPushButton:hover { 
    background-color: #0b5ed7; 
}

QPushButton:pressed { 
    background-color: #0a58ca; 
}

QPushButton:disabled { 
    background-color: #a5c8fd; 
    color: #f8f9fa; 
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    padding: 8px 12px; 
    border: 1px solid #ced4da; 
    border-radius: 6px;
    background: #ffffff; 
    selection-background-color: #0d6efd;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #86b7fe;
}

QListWidget, QTextEdit, QScrollArea {
    border: 1px solid #ced4da; 
    border-radius: 8px; 
    background: #ffffff; 
    padding: 8px;
}

QProgressBar {
    border: 1px solid #ced4da; 
    border-radius: 6px; 
    text-align: center;
    background-color: #e9ecef; 
    color: #495057; 
    font-weight: bold; 
    min-height: 20px;
}

QProgressBar::chunk { 
    background-color: #198754; 
    border-radius: 5px; 
}

QFrame { 
    background-color: #ffffff; 
    border: 1px solid #e9ecef; 
    border-radius: 8px; 
}

QLabel { 
    font-weight: 500; 
}

QScrollBar:vertical { 
    border: none; 
    background: #f8f9fa; 
    width: 10px; 
    border-radius: 5px; 
}

QScrollBar::handle:vertical { 
    background: #ced4da; 
    min-height: 20px; 
    border-radius: 5px; 
}

QScrollBar::handle:vertical:hover { 
    background: #adb5bd; 
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
    border: none; 
    background: none; 
}
"""



# ──────────────────────────────────────────────────────────
# 信号发射器 — 用于跨线程通信
# ──────────────────────────────────────────────────────────

class SignalEmitter(QObject):
    """发射日志和进度信号"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    api_status_signal = pyqtSignal(str, str)  # label, status
    done_signal = pyqtSignal(bool, int, float)


# ──────────────────────────────────────────────────────────
# GUITranslator — 接受直接传入的配置
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
        
        # 解析高级选项
        self.refine_pass = cfg.get("refine_pass", False)
        self.max_length = int(cfg.get("max_length", 40))
        self.smart_break = cfg.get("smart_break", True)
        self.punct_localize = cfg.get("punct_localize", True)
        self.enable_cache = cfg.get("enable_cache", True)
        self.cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".translation_cache.json")
        self.cache = self._load_cache()
        self.total_tokens = 0
        self.total_cost = 0.0

        self.api_configs = api_configs
        self._current_api_index = 0

        if not self.api_configs:
            raise ValueError(
                "没有可用的 API 配置。\n请在「API 设置」标签页中至少添加一个 API Key。"
            )


# ──────────────────────────────────────────────────────────
# 主窗口
# ──────────────────────────────────────────────────────────

class SubtitleTranslatorApp(QMainWindow):
    FILETYPES = [
        ("字幕文件", "*.srt *.ass *.ssa *.vtt *.sub *.lrc"),
        ("所有文件", "*.*"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Subtitle Translator By:haliang0409")
        self.setGeometry(100, 100, 900, 750)

        self._cfg = config.load()
        self.emitter = SignalEmitter()

        # 翻译线程状态
        self._stop_event = threading.Event()
        self._trans_thread: threading.Thread | None = None
        self._batch_files: list[str] = []
        self._api_status_labels: dict = {}

        # 创建 UI
        self.setStyleSheet(MODERN_STYLE)
        self._build_ui()

        # 连接信号
        self.emitter.log_signal.connect(self._append_log)
        self.emitter.progress_signal.connect(self._update_progress_ui)
        self.emitter.api_status_signal.connect(self._update_api_status_ui)
        self.emitter.done_signal.connect(self._on_translation_done)

    def _build_ui(self):
        """构建主界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)
        central_widget.setLayout(main_layout)

        # 创建标签页
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # 三个标签页
        self._build_translate_tab()
        self._build_api_tab()
        self._build_advanced_tab()

    # ── 翻译标签页 ───────────────────────────────────────

    def _build_translate_tab(self):
        """翻译标签页"""
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 输入文件
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("输入文件"))
        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("选择或拖放字幕文件...")
        self._input_field.setReadOnly(True)
        input_layout.addWidget(self._input_field)
        input_layout.addWidget(QPushButton("浏览", clicked=self._browse_input))
        layout.addLayout(input_layout)

        # 文件信息
        self._file_info_label = QLabel("")
        self._file_info_label.setStyleSheet("color: gray;")
        layout.addWidget(self._file_info_label)

        # 输出文件
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("输出文件"))
        self._output_field = QLineEdit()
        self._output_field.setPlaceholderText("留空则自动生成...")
        output_layout.addWidget(self._output_field)
        output_layout.addWidget(QPushButton("浏览", clicked=self._browse_output))
        layout.addLayout(output_layout)

        # 选项行
        options_layout = QHBoxLayout()
        options_layout.addWidget(QLabel("目标语言"))
        self._lang_field = QLineEdit()
        self._lang_field.setText(self._cfg.get("target_language", "Chinese"))
        self._lang_field.setMaximumWidth(110)
        options_layout.addWidget(self._lang_field)
        
        self._resume_check = QCheckBox("断点续传")
        self._resume_check.setChecked(True)
        options_layout.addWidget(self._resume_check)
        
        self._context_check = QCheckBox("增强上下文")
        self._context_check.setChecked(False)
        options_layout.addWidget(self._context_check)
        options_layout.addStretch()
        layout.addLayout(options_layout)

        # 批量队列
        queue_label = QLabel("批量队列")
        layout.addWidget(queue_label)
        
        queue_btn_layout = QHBoxLayout()
        queue_btn_layout.addWidget(QPushButton("添加文件", clicked=self._add_to_queue))
        queue_btn_layout.addWidget(QPushButton("清除", clicked=self._clear_queue))
        queue_btn_layout.addStretch()
        layout.addLayout(queue_btn_layout)

        self._queue_list = QListWidget()
        self._queue_list.setMaximumHeight(80)
        layout.addWidget(self._queue_list)

        # 开始/停止按钮
        self._start_btn = QPushButton("▶  开始翻译")
        self._start_btn.setMinimumHeight(40)
        self._start_btn.setStyleSheet("font-size: 16px; padding: 12px; background-color: #198754;")
        self._start_btn.clicked.connect(self._toggle_translation)
        layout.addWidget(self._start_btn)

        # 进度条
        progress_layout = QHBoxLayout()
        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        progress_layout.addWidget(self._progress_bar)

        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("color: #198754; font-weight: bold;")
        self._stats_label.hide()
        progress_layout.addWidget(self._stats_label)

        self._progress_label = QLabel("0 / 0")
        self._progress_label.setMaximumWidth(70)
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        progress_layout.addWidget(self._progress_label)
        layout.addLayout(progress_layout)

        # 日志框
        log_label = QLabel("日志")
        layout.addWidget(log_label)
        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setMaximumHeight(150)
        self._log_box.setFont(QFont("Courier New", 10))
        layout.addWidget(self._log_box, 1)

        self.tabs.addTab(tab, "翻译")

    # ── API 设置标签页 ────────────────────────────────────

    def _build_api_tab(self):
        """API 设置标签页"""
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 滚动区域
        self._api_scroll = QScrollArea()
        self._api_scroll.setWidgetResizable(True)
        self._api_container = QWidget()
        self._api_container_layout = QVBoxLayout()
        self._api_container.setLayout(self._api_container_layout)
        self._api_scroll.setWidget(self._api_container)
        layout.addWidget(self._api_scroll)

        # 加载已保存的 API
        self._api_cards: list[dict] = []
        for api in self._cfg.get("apis", []):
            self._add_api_card(api)
            
        self._api_container_layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QPushButton("+ 添加 API", clicked=self._add_api_card_empty))
        btn_layout.addWidget(QPushButton("🔌 测试全部", clicked=self._test_all_apis))
        btn_layout.addStretch()

        save_btn = QPushButton("💾  保存设置")
        save_btn.setMinimumHeight(38)
        save_btn.setStyleSheet("font-size: 13px; font-weight: bold;")
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        self.tabs.addTab(tab, "API 设置")

    def _add_api_card(self, api_data: dict | None = None):
        """添加 API 配置卡片"""
        from PyQt6.QtWidgets import QGroupBox, QFormLayout
        if api_data is None:
            api_data = {
                "key": "",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
                "disable_proxy": True,
            }

        idx = len(self._api_cards)
        card_frame = QGroupBox(f"API #{idx + 1}")
        card_frame.setStyleSheet("""
            QGroupBox {
                border: 1px solid #c0c0c0;
                border-radius: 6px;
                margin-top: 10px;
                background-color: transparent;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                font-weight: bold;
                color: #0d6efd;
            }
        """)
        
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(15, 20, 15, 15)
        card_layout.setSpacing(10)
        card_frame.setLayout(card_layout)

        # 功能区头部 (上下移, 测试, 删除)
        header_layout = QHBoxLayout()
        
        status_label = QLabel("—")
        status_label.setMinimumWidth(30)
        header_layout.addWidget(status_label)
        
        header_layout.addStretch()
        
        # 将移动和删除按钮放在右上角
        move_up_btn = QPushButton("上移")
        move_up_btn.setFixedSize(60, 28)
        move_up_btn.setStyleSheet("QPushButton { padding: 2px 5px; border-radius: 4px; }")
        move_up_btn.clicked.connect(lambda: self._move_card(card_frame, -1))
        header_layout.addWidget(move_up_btn)
        
        move_down_btn = QPushButton("下移")
        move_down_btn.setFixedSize(60, 28)
        move_down_btn.setStyleSheet("QPushButton { padding: 2px 5px; border-radius: 4px; }")
        move_down_btn.clicked.connect(lambda: self._move_card(card_frame, 1))
        header_layout.addWidget(move_down_btn)
        
        del_btn = QPushButton("删除")
        del_btn.setFixedSize(60, 28)
        del_btn.setStyleSheet("QPushButton { background-color: #dc3545; color: white; border-radius: 4px; border: none; padding: 2px 5px; } QPushButton:hover { background-color: #c82333; }")
        del_btn.clicked.connect(lambda: self._remove_api_card(card_frame))
        header_layout.addWidget(del_btn)
        
        card_layout.addLayout(header_layout)

        # 表单区域 (使用 QFormLayout 对齐体验更好)
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        key_field = QLineEdit()
        key_field.setEchoMode(QLineEdit.EchoMode.Password)
        key_field.setText(api_data.get("key", ""))
        key_field.setPlaceholderText("sk-...")
        form_layout.addRow("API Key:", key_field)
        
        url_field = QLineEdit()
        url_field.setText(api_data.get("base_url", "https://api.openai.com/v1"))
        form_layout.addRow("Base URL:", url_field)
        
        card_layout.addLayout(form_layout)

        # 模型 + 代理 + 测试 布局
        bottom_layout = QHBoxLayout()
        
        bottom_layout.addWidget(QLabel("模型:"))
        model_field = QLineEdit()
        model_field.setText(api_data.get("model", "gpt-4o-mini"))
        model_field.setMinimumWidth(150)
        bottom_layout.addWidget(model_field)

        proxy_check = QCheckBox("禁用代理")
        proxy_check.setChecked(api_data.get("disable_proxy", True))
        bottom_layout.addWidget(proxy_check)
        
        bottom_layout.addStretch()

        test_btn = QPushButton("测试接口")
        test_btn.setMinimumHeight(28)
        test_btn.setStyleSheet("QPushButton { background-color: #f8f9fa; color: #212529; border: 1px solid #ced4da; border-radius: 4px; padding: 0 10px; } QPushButton:hover { background-color: #e2e6ea; }")
        test_btn.clicked.connect(
            lambda: self._test_single_api(key_field, url_field, model_field, proxy_check, status_label)
        )
        bottom_layout.addWidget(test_btn)
        
        card_layout.addLayout(bottom_layout)

        count = self._api_container_layout.count()
        # insert before the stretch
        self._api_container_layout.insertWidget(count - 1 if count > 0 else 0, card_frame)

        card_data = {
            "card": card_frame,
            "key_field": key_field,
            "url_field": url_field,
            "model_field": model_field,
            "proxy_check": proxy_check,
            "status_label": status_label,
            "group_box": card_frame, # Store ref to group box instance
        }
        self._api_cards.append(card_data)
        self._renumber_api_cards()

    def _add_api_card_empty(self):
        """添加空的 API 卡片"""
        self._add_api_card()

    def _remove_api_card(self, card):
        """移除 API 卡片"""
        self._api_cards = [c for c in self._api_cards if c["card"] is not card]
        card.deleteLater()
        self._renumber_api_cards()

    def _renumber_api_cards(self):
        """重新编号 API 卡片"""
        for i, c in enumerate(self._api_cards):
            c["group_box"].setTitle(f"API #{i + 1}")

    def _move_card(self, card, direction: int):
        """移动 API 卡片"""
        idx = next((i for i, c in enumerate(self._api_cards) if c["card"] is card), None)
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._api_cards):
            return
        self._api_cards[idx], self._api_cards[new_idx] = self._api_cards[new_idx], self._api_cards[idx]
        
        # 重新排列
        for i, c in enumerate(self._api_cards):
            self._api_container_layout.removeWidget(c["card"])
            self._api_container_layout.insertWidget(i, c["card"])
        self._renumber_api_cards()

    # ── 高级设置标签页 ────────────────────────────────────

    def _build_advanced_tab(self):
        """高级设置标签页"""
        tab = QWidget()
        layout = QGridLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(16)
        tab.setLayout(layout)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        row = 0

        # 批次大小
        layout.addWidget(QLabel("批次大小"), row, 0)
        self._batch_spin = QSpinBox()
        self._batch_spin.setMinimum(1)
        self._batch_spin.setMaximum(100)
        self._batch_spin.setValue(self._cfg.get("batch_size", 30))
        layout.addWidget(self._batch_spin, row, 1)
        row += 1

        # 并发线程数
        layout.addWidget(QLabel("并发线程数"), row, 0)
        self._threads_spin = QSpinBox()
        self._threads_spin.setMinimum(1)
        self._threads_spin.setMaximum(32)
        self._threads_spin.setValue(self._cfg.get("num_threads", 1))
        self._threads_spin.setToolTip("多线程并发翻译，可大幅加快速度")
        layout.addWidget(self._threads_spin, row, 1)
        row += 1

        # 请求间隔
        layout.addWidget(QLabel("请求间隔 (秒)"), row, 0)
        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setMinimum(0)
        self._interval_spin.setMaximum(5)
        self._interval_spin.setValue(self._cfg.get("request_interval", 1.0))
        layout.addWidget(self._interval_spin, row, 1)
        row += 1

        # 上下文窗口
        layout.addWidget(QLabel("上下文窗口"), row, 0)
        self._context_spin = QSpinBox()
        self._context_spin.setMinimum(0)
        self._context_spin.setMaximum(20)
        self._context_spin.setValue(self._cfg.get("context_window", 5))
        layout.addWidget(self._context_spin, row, 1)
        row += 1

        # 最大重试次数
        layout.addWidget(QLabel("最大重试次数"), row, 0)
        self._retries_spin = QSpinBox()
        self._retries_spin.setMinimum(1)
        self._retries_spin.setMaximum(10)
        self._retries_spin.setValue(self._cfg.get("max_retries", 3))
        layout.addWidget(self._retries_spin, row, 1)
        row += 1

        # 重试间隔
        layout.addWidget(QLabel("重试间隔 (秒)"), row, 0)
        self._retry_delay_spin = QSpinBox()
        self._retry_delay_spin.setMinimum(1)
        self._retry_delay_spin.setMaximum(10)
        self._retry_delay_spin.setValue(self._cfg.get("retry_delay", 3))
        layout.addWidget(self._retry_delay_spin, row, 1)
        row += 1

        # 默认模型
        layout.addWidget(QLabel("默认模型"), row, 0)
        self._model_field = QLineEdit()
        self._model_field.setText(self._cfg.get("model_name", "gpt-4o-mini"))
        layout.addWidget(self._model_field, row, 1)
        row += 1

        # 二次润色模式
        layout.addWidget(QLabel("二次润色模式"), row, 0)
        self._refine_check = QCheckBox("启用二次翻译以修正语句")
        self._refine_check.setChecked(self._cfg.get("refine_pass", False))
        layout.addWidget(self._refine_check, row, 1)
        row += 1

        # 长度约束
        layout.addWidget(QLabel("最大单行字符数"), row, 0)
        self._max_length_spin = QSpinBox()
        self._max_length_spin.setRange(0, 200)
        self._max_length_spin.setSpecialValueText("0 (无限制)")
        self._max_length_spin.setValue(self._cfg.get("max_length", 40))
        layout.addWidget(self._max_length_spin, row, 1)
        row += 1

        # 智能断行
        layout.addWidget(QLabel("智能断行"), row, 0)
        self._smart_break_check = QCheckBox("遇长句时自动换行")
        self._smart_break_check.setChecked(self._cfg.get("smart_break", True))
        layout.addWidget(self._smart_break_check, row, 1)
        row += 1

        # 标点本地化
        layout.addWidget(QLabel("标点本地化"), row, 0)
        self._punct_localize_check = QCheckBox("转换为中文全角标点")
        self._punct_localize_check.setChecked(self._cfg.get("punct_localize", True))
        layout.addWidget(self._punct_localize_check, row, 1)
        row += 1

        # 缓存机制
        layout.addWidget(QLabel("启用翻译缓存"), row, 0)
        self._enable_cache_check = QCheckBox("再次翻译相同内容时直接返回")
        self._enable_cache_check.setChecked(self._cfg.get("enable_cache", True))
        layout.addWidget(self._enable_cache_check, row, 1)
        row += 1

        # 输出格式转换
        layout.addWidget(QLabel("输出格式转换"), row, 0)
        self._format_combo = QComboBox()
        self._format_combo.addItems(["与输入相同", ".srt", ".ass", ".vtt", ".lrc", ".sub"])
        layout.addWidget(self._format_combo, row, 1)
        row += 1

        # 全局禁用代理
        self._global_proxy_check = QCheckBox("全局禁用代理")
        self._global_proxy_check.setChecked(self._cfg.get("disable_proxy", True))
        layout.addWidget(self._global_proxy_check, row, 0, 1, 2)
        row += 1

        # 最近文件
        layout.addWidget(QLabel("最近文件"), row, 0)
        clear_recent_btn = QPushButton("清除历史", clicked=self._clear_recent)
        clear_recent_btn.setMaximumWidth(100)
        layout.addWidget(clear_recent_btn, row, 1, alignment=Qt.AlignmentFlag.AlignRight)
        row += 1

        self._recent_list = QListWidget()
        self._recent_list.setMaximumHeight(100)
        self._refresh_recent_list()
        layout.addWidget(self._recent_list, row, 0, 1, 2)
        row += 1

        # 保存按钮
        save_btn = QPushButton("💾  保存设置")
        save_btn.setMinimumHeight(38)
        save_btn.setStyleSheet("font-size: 13px; font-weight: bold;")
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn, row + 1, 0, 1, 2)

        layout.setRowStretch(row, 1)

        self.tabs.addTab(tab, "高级设置")

    # ── 文件操作 ──────────────────────────────────────────

    def _browse_input(self):
        """浏览输入文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择字幕文件",
            filter="字幕文件 (*.srt *.ass *.ssa *.vtt *.sub *.lrc);;所有文件 (*.*)"
        )
        if path:
            self._input_field.setText(path)
            self._update_file_info(path)

    def _browse_output(self):
        """浏览输出文件"""
        path, _ = QFileDialog.getSaveFileName(
            self, "选择输出路径",
            filter="字幕文件 (*.srt *.ass *.ssa *.vtt *.sub *.lrc);;所有文件 (*.*)",
            defaultSuffix="srt"
        )
        if path:
            self._output_field.setText(path)

    def _update_file_info(self, path: str):
        """更新文件信息"""
        if not path or not os.path.exists(path):
            self._file_info_label.setText("")
            return

        ext = os.path.splitext(path)[1].lower()
        try:
            if ext != ".lrc":
                subs = pysubs2.load(path)
                count = len(subs)
                self._file_info_label.setText(f"格式：{ext.upper().lstrip('.')}  |  共 {count} 条字幕")
            else:
                self._file_info_label.setText("格式：LRC 歌词文件")
        except Exception:
            self._file_info_label.setText(f"格式：{ext.upper().lstrip('.')}")

        # 自动生成输出路径
        if not self._output_field.text():
            base, file_ext = os.path.splitext(path)
            self._output_field.setText(f"{base}_translated{file_ext}")

    def _add_to_queue(self):
        """添加文件到批量队列"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "添加到批量队列",
            filter="字幕文件 (*.srt *.ass *.ssa *.vtt *.sub *.lrc);;所有文件 (*.*)"
        )
        for p in paths:
            if p not in self._batch_files:
                self._batch_files.append(p)
        self._update_queue_display()

    def _clear_queue(self):
        """清除批量队列"""
        self._batch_files.clear()
        self._update_queue_display()

    def _update_queue_display(self):
        """更新队列显示"""
        self._queue_list.clear()
        for i, f in enumerate(self._batch_files):
            item = QListWidgetItem(f"{i + 1}. {os.path.basename(f)}")
            self._queue_list.addItem(item)

    # ── API 操作 ──────────────────────────────────────────

    def _get_api_configs(self) -> list:
        """获取 API 配置"""
        configs = []
        for i, c in enumerate(self._api_cards):
            key = c["key_field"].text().strip()
            if not key:
                continue
            configs.append({
                "key": key,
                "base_url": c["url_field"].text().strip().rstrip("/"),
                "model": c["model_field"].text().strip() or self._model_field.text().strip() or "gpt-4o-mini",
                "proxies": {"http": None, "https": None} if c["proxy_check"].isChecked() else None,
                "label": f"API-{i + 1}",
            })
        return configs

    def _test_single_api(self, key_field, url_field, model_field, proxy_check, status_label):
        """测试单个 API"""
        key = key_field.text().strip()
        if not key:
            QMessageBox.warning(self, "API Key 为空", "请先填写 API Key")
            return
        
        status_label.setText("⏳")
        t = threading.Thread(
            target=self._test_api_worker,
            args=(key, url_field.text().strip(), model_field.text().strip(),
                  proxy_check.isChecked(), status_label),
            daemon=True,
        )
        t.start()

    def _test_all_apis(self):
        """测试所有 API"""
        for c in self._api_cards:
            if c["key_field"].text().strip():
                self._test_single_api(
                    c["key_field"], c["url_field"], c["model_field"],
                    c["proxy_check"], c["status_label"],
                )

    def _test_api_worker(self, key: str, base_url: str, model: str,
                         disable_proxy: bool, status_label):
        """API 测试工作线程"""
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
            self.emitter.api_status_signal.emit(str(id(status_label)), "✅")
            self.emitter.log_signal.emit(f"✅ [{model}] 连接成功：{content[:60]}")
        except Exception as e:
            self.emitter.api_status_signal.emit(str(id(status_label)), "❌")
            self.emitter.log_signal.emit(f"❌ [{model}] 连接失败：{e}")

    def _update_api_status_ui(self, label_id, status):
        """更新 API 状态 UI"""
        for c in self._api_cards:
            if str(id(c["status_label"])) == label_id:
                c["status_label"].setText(status)
                break

    # ── 翻译控制 ──────────────────────────────────────────

    def _toggle_translation(self):
        """切换翻译状态"""
        if self._trans_thread and self._trans_thread.is_alive():
            self._stop_event.set()
            self._start_btn.setEnabled(False)
            self._start_btn.setText("正在停止...")
        else:
            inp = self._input_field.text().strip()
            if not inp and not self._batch_files:
                QMessageBox.warning(self, "未选择文件", "请先选择输入文件或添加批量队列")
                return
            
            self._stop_event.clear()
            self._start_btn.setText("⏹  停止翻译")
            self._start_btn.setStyleSheet("font-size: 16px; padding: 12px; background-color: #dc3545;")
            self._progress_bar.setValue(0)
            self._stats_label.hide()
            self._progress_label.setText("0 / 0")
            self._log_box.clear()
            
            self._trans_thread = threading.Thread(target=self._run_translation, daemon=True)
            self._trans_thread.start()

    def _run_translation(self):
        """运行翻译"""
        api_configs = self._get_api_configs()
        cfg = self._get_current_cfg()

        try:
            translator = GUITranslator(api_configs, cfg)
        except ValueError as e:
            self._log(f"❌ {e}")
            self.emitter.done_signal.emit(False, 0, 0.0)
            return

        # 构建文件列表
        inp = self._input_field.text().strip()
        files: list[tuple[str, str]] = []
        if inp and os.path.exists(inp):
            out = self._output_field.text().strip()
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
            self.emitter.done_signal.emit(False, translator.total_tokens, translator.total_cost)
            return

        enhanced = self._context_check.isChecked()
        resume = self._resume_check.isChecked()
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
            translator.target_lang = self._lang_field.text().strip() or cfg["target_language"]
            self._translate_file(translator, inp_f, out_f, enhanced, resume)

        self.emitter.done_signal.emit(True, translator.total_tokens, translator.total_cost)

    def _translate_file(self, translator: GUITranslator, input_file: str,
                        output_file: str, enhanced_context: bool, resume: bool) -> bool:
        """翻译单个文件"""
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
        num_threads = self._threads_spin.value()
        self._update_progress(start_index, total)

        remaining = total - start_index
        num_threads = max(1, min(num_threads, remaining))
        if num_threads > 1:
            self._log(f"🚀 使用 {num_threads} 个线程并发翻译")

        def _gui_translate_chunk(chunk_start, chunk_end):
            """单个线程翻译一段范围的字幕"""
            for i in range(chunk_start, chunk_end, batch_size):
                if self._stop_event.is_set():
                    return

                batch_end_idx = min(i + batch_size, chunk_end)
                batch_texts = all_originals[i:batch_end_idx]

                if enhanced_context:
                    ctx_start = max(0, i - translator.context_window)
                    ctx_before = [
                        (all_originals[j], all_translations[j])
                        for j in range(ctx_start, i)
                        if all_translations[j]
                    ]
                    ctx_end = min(total, batch_end_idx + translator.context_window)
                    ctx_after = all_originals[batch_end_idx:ctx_end]
                    translated = translator.translate_batch_with_context(
                        batch_texts, ctx_before, ctx_after
                    )
                else:
                    translated = translator.translate_batch(batch_texts)

                for j, text in enumerate(translated):
                    idx = i + j
                    if idx < total:
                        all_translations[idx] = text

                with progress_lock:
                    nonlocal completed_count
                    completed_count += len(batch_texts)
                    self._update_progress(start_index + completed_count, total)
                    self._log(f"✓ {start_index + completed_count}/{total} 条完成")

                # 可中断的等待
                if batch_end_idx < chunk_end and translator.request_interval > 0:
                    elapsed = 0.0
                    while elapsed < translator.request_interval:
                        if self._stop_event.is_set():
                            return
                        time.sleep(0.1)
                        elapsed += 0.1

        try:
            progress_lock = threading.Lock()
            completed_count = 0

            if num_threads <= 1:
                _gui_translate_chunk(start_index, total)
            else:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                chunk_size = remaining // num_threads
                chunks = []
                for t in range(num_threads):
                    c_start = start_index + t * chunk_size
                    c_end = start_index + (t + 1) * chunk_size if t < num_threads - 1 else total
                    if c_start < c_end:
                        chunks.append((c_start, c_end))

                with ThreadPoolExecutor(max_workers=num_threads) as executor:
                    futures = {
                        executor.submit(_gui_translate_chunk, c_start, c_end): (c_start, c_end)
                        for c_start, c_end in chunks
                    }
                    for future in as_completed(futures):
                        exc = future.exception()
                        if exc:
                            raise TranslationError(f"线程翻译失败：{exc}")

        except TranslationError as e:
            self._log(f"❌ 翻译中止：{e}")
            return False

        if self._stop_event.is_set():
            # Save partial progress
            for idx in range(total):
                if all_translations[idx] is not None:
                    subs[idx].text = all_translations[idx].replace(" [BR] ", "\n").replace("[BR]", "\n")
            translated_count = sum(1 for t in all_translations if t is not None)
            translator._save_progress(output_file, translated_count, subs)
            self._log(f"⏸ 已中断，进度保存至 {translated_count}/{total}")
            return False

        # Apply translations to subs
        for idx in range(start_index, total):
            if all_translations[idx] is not None:
                subs[idx].text = all_translations[idx].replace(" [BR] ", "\n").replace("[BR]", "\n")

        # 格式转换（如有）
        out_fmt = self._format_combo.currentText()
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
        """记录日志"""
        ts = datetime.now().strftime("%H:%M:%S")
        self.emitter.log_signal.emit(f"[{ts}] {message}")

    def _append_log(self, text: str):
        """添加日志到显示"""
        self._log_box.append(text)
        # 滚动到底部
        scroll_bar = self._log_box.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def _update_progress(self, current: int, total: int):
        """更新进度"""
        self.emitter.progress_signal.emit(current, total)

    def _update_progress_ui(self, current: int, total: int):
        """更新进度 UI"""
        if total > 0:
            self._progress_bar.setValue(current * 100 // total)
        else:
            self._progress_bar.setValue(0)
        self._progress_label.setText(f"{current} / {total}")

    def _on_translation_done(self, success: bool, tokens: int = 0, cost: float = 0.0):
        """翻译完成"""
        if tokens > 0 or cost > 0:
            self._stats_label.setText(f"Tokens: {tokens} | Cost: ${cost:.5f}")
            self._stats_label.show()
            self._log(f"\n💰 预计消耗: {tokens} Tokens (约 ${cost:.5f})")

        self._start_btn.setText("▶  开始翻译")
        self._start_btn.setStyleSheet("font-size: 16px; padding: 12px; background-color: #198754;")
        self._start_btn.setEnabled(True)
        self._refresh_recent_list()

    # ── 设置管理 ──────────────────────────────────────────

    def _get_current_cfg(self) -> dict:
        """获取当前配置"""
        return {
            "target_language": self._lang_field.text().strip() or "Chinese",
            "model_name": self._model_field.text().strip(),
            "batch_size": self._batch_spin.value(),
            "num_threads": self._threads_spin.value(),
            "request_interval": round(self._interval_spin.value(), 2),
            "context_window": self._context_spin.value(),
            "max_retries": self._retries_spin.value(),
            "retry_delay": self._retry_delay_spin.value(),
            "disable_proxy": self._global_proxy_check.isChecked(),
            "refine_pass": self._refine_check.isChecked(),
            "max_length": self._max_length_spin.value(),
            "smart_break": self._smart_break_check.isChecked(),
            "punct_localize": self._punct_localize_check.isChecked(),
            "enable_cache": self._enable_cache_check.isChecked(),
        }

    def _save_settings(self):
        """保存设置"""
        data = config.load()

        data["apis"] = [
            {
                "key": c["key_field"].text().strip(),
                "base_url": c["url_field"].text().strip(),
                "model": c["model_field"].text().strip(),
                "disable_proxy": c["proxy_check"].isChecked(),
            }
            for c in self._api_cards
        ]

        data.update(self._get_current_cfg())

        config.save(data)
        QMessageBox.information(self, "已保存", "设置已保存到 config.json")

    def _clear_recent(self):
        """清除最近文件"""
        data = config.load()
        data["recent_files"] = []
        config.save(data)
        self._refresh_recent_list()

    def _refresh_recent_list(self):
        """刷新最近文件列表"""
        self._recent_list.clear()
        recent = config.load().get("recent_files", [])
        if not recent:
            item = QListWidgetItem("暂无记录")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._recent_list.addItem(item)
            return
        
        for path in recent:
            item_widget = QWidget()
            item_layout = QHBoxLayout()
            item_layout.setContentsMargins(0, 0, 0, 0)
            
            label = QLabel(os.path.basename(path))
            label.setToolTip(path)
            item_layout.addWidget(label)
            item_layout.addStretch()
            
            load_btn = QPushButton("载入")
            load_btn.setMaximumWidth(60)
            load_btn.clicked.connect(lambda p=path: self._load_recent(p))
            item_layout.addWidget(load_btn)
            
            item_widget.setLayout(item_layout)
            item = QListWidgetItem()
            item.setSizeHint(item_widget.sizeHint())
            self._recent_list.addItem(item)
            self._recent_list.setItemWidget(item, item_widget)

    def _load_recent(self, path: str):
        """从最近文件加载"""
        if os.path.exists(path):
            self._input_field.setText(path)
            self._output_field.setText("")
            self._update_file_info(path)
            self.tabs.setCurrentIndex(0)
        else:
            QMessageBox.critical(self, "文件不存在", f"文件已移动或删除：\n{path}")
            data = config.load()
            data["recent_files"] = [f for f in data.get("recent_files", []) if f != path]
            config.save(data)
            self._refresh_recent_list()


# ──────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    window = SubtitleTranslatorApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
