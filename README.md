# AI 字幕翻译工具

基于 Python 和 PyQt6 构建的高级 AI 字幕翻译工具，调用任何兼容 OpenAI 接口的模型（如 OpenAI、DeepSeek、Claude、本地 LLM 等）进行字幕的精准翻译，提供**命令行 (CLI)** 和**图形界面 (GUI)** 两种使用方式。

## 功能特性

- ✅ **现代图形界面**：基于 PyQt6 的专业界面，提供跨平台体验（Windows/macOS/Linux）。
- ✅ **支持多种格式**：SRT、ASS、SSA、VTT、SUB、LRC 等主流格式的无缝解析与保存。
- ✅ **多模型与高可用 fallback**：配置多组 API Key 和 Base URL，当遇到网络限流或接口拥堵时，自动切换下一组模型继续进行请求。
- ✅ **全局重试与单行兜底重试**：当大段字幕批量解析失败时，自动降级为“单句精确请求”，极大程度避免整段翻译报废重来的窘境。
- ✅ **二次润色模式 (Refine Pass)**：发送二次请求专门对翻译结果结构进行母语化修正，让生硬的机翻更自然。
- ✅ **阅读速度控制 & 自动断行**：支持设定单行最大字符数，长句智能预测语言停顿并在合适位置生成字幕断行。
- ✅ **标点本地化**：翻译出中文字幕时，将英文的半角标点自动替换为符合语法的全角标点。
- ✅ **翻译记忆缓存**：自动基于本地原文 Hash 生成缓存文件，相同句子的重复翻译瞬间完成，节省 token 成本。
- ✅ **成本统计与 Token 预估**：内置 `tiktoken` 支持，实时预估每次翻译所消耗的 Input/Output Token，并结合标准费率折算美金成本（GUI 进度条实时展示）。
- ✅ **增强上下文模式**：通过滑动窗口技术读取上下文，使翻译具有剧情连贯性和指代准确性。
- ✅ **多线程并发翻译**：将字幕切分为若干段，同时以多个线程并发请求 API，配合多 API 轮询可成倍加快翻译速度。
- ✅ **断点续传**：支持随时中断，重启时接续上次完成的进度进行翻译。

## 安装

```bash
# 1. 下载代码并进入目录
git clone https://github.com/haliang0409/ai-subtitle-translate.git
cd ai-subtitle-translate

# 2. 创建并激活虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖 (包含 PyQt6, requests, pysubs2, tiktoken 等)
pip install -r requirements.txt
```

## 配置 & 启动

### 方式一：图形界面 (GUI) 配置（推荐）

直接启动 GUI 程序后，在「API 设置」和「高级设置」标签页中修改选项并点击「保存设置」，配置将持久化保存在根目录的 `config.json` 中。

```bash
python gui_pyqt.py
# 或
python main.py
```

**GUI 操作指南：**
1. **翻译 Tab**：选择输入文件 -> 调整配置 -> 加入批量队列或直接点击「▶ 开始翻译」。右侧进度条在完成后会显示具体 Token 消耗和估算成本。
2. **API 设置 Tab**：可自由添加、上下调整优先级、删除和单独测试各 API 线路。
3. **高级设置 Tab**：可配置 批次大小、**并发线程数**、重试时间、二次润色、阅读控制(最大行长度)、标点替换、缓存等进阶 NLP 翻译功能。

### 方式二：环境变量与命令行 (CLI) 配置

您可以将 `.env.example` 复制为 `.env` 并直接填写 API 信息，程序在没有 `config.json` 或使用命令行时将默认读取它：

```dotenv
# 多 API 配置示例（支持轮询可用）
API_1_KEY=sk-your-first-key
API_1_BASE_URL=https://api.openai.com/v1
API_1_MODEL=gpt-4o-mini

API_2_KEY=sk-your-second-key
API_2_BASE_URL=https://api.deepseek.com
API_2_MODEL=deepseek-chat
```

#### 命令行运行翻译

```bash
# 测试各个 API 的连接延迟和可用性
python main.py --test

# 基本用法（将自动输出到 your_subtitle_translated.srt 并打印花费统计）
python main.py your_subtitle.srt

# 指定输出路径和目标语言
python main.py your_subtitle.srt -o output.srt -l "Traditional Chinese"

# 指定批次大小
python main.py your_subtitle.srt -b 50

# 启用增强上下文模式
python main.py your_subtitle.srt --context

# 使用 4 个并发线程加速翻译（适合字幕条数多、API 限速宽松的场景；多 API 通过 .env 配置）
python main.py your_subtitle.srt -t 4

# 忽略之前因为中断而生成的 .progress 进度文件，强制从头开始
python main.py your_subtitle.srt --no-resume
```

## 支持的字幕格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| SubRip | `.srt` | 最常见的字幕格式 |
| Advanced SSA | `.ass` | 支持样式和特效 |
| SubStation Alpha | `.ssa` | ASS 的前身 |
| WebVTT | `.vtt` | Web 视频字幕 |
| MicroDVD | `.sub` | 基于帧的字幕 |
| LRC | `.lrc` | 歌词文件 |

## 开源协议

MIT License

## 项目结构

```
ai-subtitle-translate/
├── gui_pyqt.py       # ✨ PyQt6 图形界面（推荐）
├── main.py           # 入口脚本（支持 CLI 和 GUI 两种模式）
├── translator.py     # 核心翻译逻辑
├── config.py         # GUI 配置管理
├── config.json       # GUI 配置文件（自动生成）
├── requirements.txt  # Python 依赖
├── .env              # 命令行环境配置（需自行创建）
├── .env.example      # 配置模板
└── README.md         # 本文档
```

## 故障排除

### Connection error / 无法连接

1. **代理问题**：本地 API 建议勾选「禁用代理」或设置 `DISABLE_PROXY=true`
2. **地址错误**：检查 Base URL 是否正确（注意 `/v1` 后缀）
3. **服务未启动**：确认本地 API 服务已运行

```bash
# 用 curl 手动测试 API
curl https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hi"}]}'
```

### 429 Too Many Requests（限流）

1. 增大「请求间隔」（建议 2.0 秒以上）
2. 减小「批次大小」（如 15~20）
3. 程序会自动按设置的次数重试
4. **多线程时触发限流**：减少并发线程数，或增加请求间隔；也可配置多组 API Key 以分担请求压力

### GUI 无法启动

确认已在虚拟环境内安装 PyQt。