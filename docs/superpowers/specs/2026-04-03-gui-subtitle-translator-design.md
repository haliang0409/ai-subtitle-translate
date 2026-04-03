# GUI 字幕翻译工具 设计文档

**日期：** 2026-04-03  
**状态：** 已批准  

---

## 概述

为现有 CLI 字幕翻译工具（`main.py` + `translator.py`）新增一个基于 customtkinter 的图形界面，完整覆盖所有 CLI 功能，并扩展多项 GUI 专属增强功能。同时汉化 `.env.example` 配置注释，并更新 `README.md`。

---

## 架构

### 文件结构

```
ai-subtitle-translate/
├── gui.py          # 新增 — 主窗口，三 Tab UI，线程调度
├── config.py       # 新增 — 配置管理，读写 config.json
├── config.json     # 自动生成 — 持久化设置（不纳入版本控制）
├── translator.py   # 现有 — 零改动
├── main.py         # 现有 CLI — 零改动
├── .env.example    # 修改 — 汉化注释
├── README.md       # 修改 — 更新内容，加入 GUI 使用说明
└── requirements.txt # 修改 — 新增 customtkinter
```

### config.json 结构

```json
{
  "apis": [
    {
      "key": "",
      "base_url": "https://api.openai.com/v1",
      "model": "gpt-4o-mini",
      "disable_proxy": true
    }
  ],
  "target_language": "Chinese",
  "model_name": "gpt-4o-mini",
  "batch_size": 30,
  "request_interval": 1.0,
  "context_window": 5,
  "max_retries": 3,
  "retry_delay": 3,
  "disable_proxy": true,
  "theme": "system",
  "recent_files": []
}
```

---

## config.py

职责：读写 `config.json`（存于脚本同目录）。

- `load() -> dict` — 读取配置，缺失字段用默认值填补
- `save(data: dict)` — 写入配置
- `DEFAULT_CONFIG` — 全量默认值常量
- `add_recent_file(path: str)` — 在列表头部插入，最多保留 10 条
- 不依赖任何 UI 模块，纯数据层

---

## gui.py

### 主窗口

- `ctk.CTk`，标题「AI 字幕翻译工具」，固定最小尺寸 680×520
- `ctk.set_appearance_mode("system")` — 跟随系统主题（可在高级设置中覆盖）
- `ctk.CTkTabview` 管理三个 Tab

### Tab 1：翻译

| 控件 | 说明 |
|---|---|
| 输入文件区 | 支持拖放和「浏览」按钮；选中后显示格式与行数预估 |
| 输出文件区 | 默认自动生成路径，可手动「浏览」覆盖 |
| 目标语言 | `CTkEntry`，快速覆盖，默认从 config 读取 |
| 断点续传 | `CTkCheckBox` |
| 增强上下文 | `CTkCheckBox` |
| 开始/停止 | 单按钮，翻译中变为「停止」；停止通过 `threading.Event` 信号 |
| 进度条 | `CTkProgressBar` + 「X / Y 条 (Z%)」标签 |
| 日志框 | `CTkTextbox`（只读，自动滚动，带时间戳） |
| 批量队列 | 列表框显示多个待翻译文件，可添加/移除，按顺序依次翻译 |

### Tab 2：API 设置

| 控件 | 说明 |
|---|---|
| API 列表 | `CTkScrollableFrame`，每条为独立卡片 |
| 每条卡片 | Key（遮掩）、Base URL、模型名、禁用代理开关、连接状态指示（✅/❌/—）、删除按钮、上移/下移按钮 |
| 添加 API | 在列表底部插入新空白条目 |
| 测试全部 | 依次测试所有 API，更新各自状态 |
| 测试此条 | 仅测试当前行 |

### Tab 3：高级设置

| 控件 | 说明 |
|---|---|
| 批次大小 | `CTkSlider` (1–100) + `CTkEntry` 联动 |
| 请求间隔 | `CTkSlider` (0–5s, 步长 0.1) + `CTkEntry` 联动 |
| 上下文窗口 | `CTkSlider` (0–20) + `CTkEntry` 联动 |
| 最大重试 | `CTkEntry` |
| 重试间隔 | `CTkEntry` |
| 全局禁用代理 | `CTkCheckBox` |
| 默认模型 | `CTkEntry` |
| 输出格式转换 | 下拉选择输出格式（SRT/ASS/VTT/LRC），默认与输入格式相同 |
| 最近文件 | 列表显示最近 10 条，点击快速载入；「清除」按钮 |
| 主题 | `CTkSegmentedButton`（跟随系统 / 浅色 / 深色） |
| 保存设置 | 写入 config.json |

---

## 线程模型

- 翻译任务运行在 `threading.Thread(daemon=True)`
- 日志消息通过 `queue.Queue` 从翻译线程传递到主线程（线程安全）
- 主线程通过 `root.after(100, _poll_log_queue)` 轮询队列并更新日志框
- 停止按钮设置 `threading.Event`；translator 在批次间检查该事件
- 翻译线程结束后，通过队列发送哨兵消息通知主线程恢复 UI 状态

**注意：** GUI 不调用 `translator.translate()`，而是直接调用 `translate_batch()` / `translate_batch_with_context()`，在 `gui.py` 内实现批次循环。这样可以在每批次之间检查 stop event，并精确更新进度条和日志。`translator.py` 仍零改动。

---

## 额外增强（超出 CLI 功能）

1. **拖放输入文件** — 无需浏览器文件选择
2. **批量翻译队列** — 多文件依次处理
3. **行数预估** — 选文件后立即显示字幕条数
4. **实时日志** — 带时间戳，自动滚动
5. **停止按钮** — 中途中断并保存进度
6. **API 优先级排序** — 上移/下移调整轮询顺序
7. **单条 API 测试** — 不需要测试全部
8. **格式转换输出** — 输入 SRT 可直接输出 ASS
9. **最近文件历史** — 快速重载
10. **主题切换** — 跟随系统/浅色/深色

---

## 需修改的现有文件

### `.env.example`
将所有英文注释翻译为中文。

### `README.md`
- 添加 GUI 启动方式（`python gui.py`）
- 更新安装说明（含 `customtkinter`）
- 保留现有 CLI 文档
- 汉化主要说明段落

### `requirements.txt`
添加 `customtkinter`。

---

## 不在范围内

- 翻译记忆库 / 术语表（可作后续功能）
- 打包为独立可执行文件（.app / .exe）
- 云端配置同步
