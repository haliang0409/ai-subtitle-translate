# AI 字幕翻译工具

使用 OpenAI 兼容 API 翻译字幕文件的 Python 工具，提供**命令行**和**图形界面**两种使用方式。

## 功能特性

- ✅ 支持多种字幕格式：**SRT、ASS、SSA、VTT、SUB、LRC**
- ✅ 支持任何 OpenAI 兼容的 API（OpenAI、DeepSeek、本地 LLM 等）
- ✅ **多 API 轮询**：配置多组 API，自动轮流使用，单组失败自动切换
- ✅ **图形界面 (GUI)**：基于 customtkinter，支持深色/浅色/跟随系统主题
- ✅ 批量翻译，减少 API 调用次数
- ✅ **增强上下文模式**：滑动窗口技术，保持翻译连贯性
- ✅ 自动重试机制（失败后等待重试，最多 N 次）
- ✅ 断点续传（中断后可继续翻译）
- ✅ 请求间隔控制，避免触发限流
- ✅ **格式转换**：输入 SRT，输出 ASS 等（GUI 支持）
- ✅ **批量队列**：GUI 支持多文件依次翻译
- ✅ 最近文件历史（GUI 快速重载）

## 安装

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

## 配置

### 方式一：图形界面配置（推荐）

启动 GUI 后，在「API 设置」标签页填写 API 信息，点击「保存设置」即可。配置保存在同目录的 `config.json`，无需手动编辑文件。

### 方式二：环境变量配置（命令行）

复制 `.env.example` 为 `.env` 并填写：

```bash
cp .env.example .env
```

#### 多 API 配置（推荐）

```dotenv
API_1_KEY=sk-your-first-key
API_1_BASE_URL=https://api.openai.com/v1
API_1_MODEL=gpt-4o-mini

API_2_KEY=sk-your-second-key
API_2_BASE_URL=https://api.deepseek.com
API_2_MODEL=deepseek-chat
```

#### 单 API 配置（兼容旧版）

```dotenv
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini
TARGET_LANGUAGE=Chinese
```

#### 环境变量说明

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `API_N_KEY` | — | 第 N 组 API 密钥 |
| `API_N_BASE_URL` | `https://api.openai.com/v1` | 第 N 组 API 端点 |
| `API_N_MODEL` | 同 `MODEL_NAME` | 第 N 组使用的模型 |
| `API_N_DISABLE_PROXY` | 同 `DISABLE_PROXY` | 第 N 组代理设置 |
| `TARGET_LANGUAGE` | `Chinese` | 翻译目标语言 |
| `MODEL_NAME` | `gpt-4o-mini` | 默认模型（备用） |
| `BATCH_SIZE` | `30` | 每批翻译的字幕条数 |
| `REQUEST_INTERVAL` | `1.0` | 请求间隔（秒） |
| `CONTEXT_WINDOW` | `5` | 增强上下文窗口大小 |
| `DISABLE_PROXY` | `true` | 是否禁用代理 |

## 使用方法

### 图形界面（GUI）

```bash
python gui.py
```

#### 翻译 Tab
1. 点击「浏览」选择输入字幕文件（显示格式和条数）
2. 输出路径自动生成，也可手动指定
3. 设置目标语言（可覆盖保存的设置）
4. 勾选所需选项：断点续传、增强上下文
5. 通过「批量队列」添加多个文件，依次翻译
6. 点击「▶ 开始翻译」；翻译中可点「⏹ 停止翻译」随时中断

#### API 设置 Tab
- 动态添加/删除/排序多组 API 配置
- 每条可单独「测试」连接；「测试全部」批量验证

#### 高级设置 Tab
- 调整批次大小、请求间隔、上下文窗口等参数（滑块联动）
- 设置输出格式转换（如 SRT → ASS）
- 管理最近文件历史
- 切换界面主题（跟随系统 / 浅色 / 深色）
- 点击「💾 保存设置」持久化到 `config.json`

---

### 命令行（CLI）

#### 测试 API 连接

```bash
python main.py --test
```

#### 翻译字幕文件

```bash
# 基本用法（输出到 input_translated.srt）
python main.py your_subtitle.srt

# 指定输出路径
python main.py your_subtitle.srt -o output.srt

# 指定目标语言
python main.py your_subtitle.srt -l Japanese

# 指定批次大小
python main.py your_subtitle.srt -b 50

# 启用增强上下文模式
python main.py your_subtitle.srt --context

# 忽略进度，从头翻译
python main.py your_subtitle.srt --no-resume
```

#### 命令行参数

| 参数 | 简写 | 说明 |
|------|------|------|
| `input` | — | 输入文件路径 |
| `--output` | `-o` | 输出文件路径（默认：`input_translated.srt`）|
| `--lang` | `-l` | 目标语言（覆盖 .env 配置）|
| `--batch` | `-b` | 批次大小（覆盖 .env 配置）|
| `--test` | — | 测试所有 API 连接 |
| `--context` | — | 启用增强上下文模式 |
| `--no-resume` | — | 忽略之前进度，从头翻译 |

## 支持的字幕格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| SubRip | `.srt` | 最常见的字幕格式 |
| Advanced SSA | `.ass` | 支持样式和特效 |
| SubStation Alpha | `.ssa` | ASS 的前身 |
| WebVTT | `.vtt` | Web 视频字幕 |
| MicroDVD | `.sub` | 基于帧的字幕 |
| LRC | `.lrc` | 歌词文件 |

## 翻译模式

### 标准模式（默认）

每批独立翻译，速度快，适合大多数场景。

### 增强上下文模式（`--context` / GUI 勾选）

使用滑动窗口，翻译时提供前后文，显著提升连贯性。适合：
- 对话密集的影视字幕
- 需要保持角色语气一致的场景
- 有大量代词指代的内容

可通过 `CONTEXT_WINDOW` 或 GUI 高级设置调整窗口大小（默认 5）。

## 断点续传

程序每翻译完一批自动保存进度（`.progress` 文件）：

- **CLI**：重新运行相同命令，程序询问是否继续
- **GUI**：勾选「断点续传」后，自动从上次中断位置继续
- 翻译完成后 `.progress` 文件自动清除

## 多 API 轮询

配置多组 API 后：

1. 每次 API 请求自动轮流使用各组 API
2. 某组连续失败（达到最大重试次数）后自动切换到下一组
3. 所有 API 均失败时才中止翻译
4. GUI 支持可视化管理：增删排序，单独测试连接状态

## 项目结构

```
ai-subtitle-translate/
├── gui.py            # 图形界面入口
├── main.py           # 命令行入口
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

### GUI 无法启动

确认已安装 customtkinter：

```bash
pip install customtkinter
```

## License

MIT
