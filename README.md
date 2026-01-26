# SRT Translator

使用 OpenAI 兼容 API 翻译 `.srt` 字幕文件的 Python 工具。

## 功能特性

- ✅ 支持任何 OpenAI 兼容的 API（OpenAI、DeepSeek、本地 LLM 等）
- ✅ 批量翻译，减少 API 调用次数
- ✅ 自动重试机制（失败后等待 3 秒重试，最多 3 次）
- ✅ 断点续传（中断后可继续翻译）
- ✅ 请求间隔控制，避免触发限流
- ✅ 进度条显示

## 安装

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

### 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `OPENAI_API_KEY` | ✅ | - | API 密钥 |
| `OPENAI_BASE_URL` | ✅ | `https://api.openai.com/v1` | API 端点地址 |
| `MODEL_NAME` | ❌ | `gpt-4o-mini` | 使用的模型名称 |
| `TARGET_LANGUAGE` | ❌ | `Chinese` | 目标翻译语言 |
| `BATCH_SIZE` | ❌ | `30` | 每次 API 调用翻译的字幕条数 |
| `REQUEST_INTERVAL` | ❌ | `1.0` | API 请求间隔（秒），防止限流 |
| `DISABLE_PROXY` | ❌ | `true` | 是否禁用代理（本地 API 建议 `true`） |

### 配置示例

**使用本地 API（如 LM Studio、Ollama）：**
```dotenv
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=http://127.0.0.1:8045/v1
MODEL_NAME=claude-sonnet-4-5-thinking
TARGET_LANGUAGE=Chinese
BATCH_SIZE=50
REQUEST_INTERVAL=1.0
DISABLE_PROXY=true
```

**使用 OpenAI 官方 API：**
```dotenv
OPENAI_API_KEY=sk-your-openai-key
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini
TARGET_LANGUAGE=Chinese
BATCH_SIZE=30
REQUEST_INTERVAL=1.0
DISABLE_PROXY=false
```

**使用 DeepSeek：**
```dotenv
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-chat
TARGET_LANGUAGE=Chinese
BATCH_SIZE=30
REQUEST_INTERVAL=1.0
DISABLE_PROXY=false
```

## 使用方法

### 测试 API 连接

```bash
python main.py --test
```

### 翻译字幕文件

```bash
# 基本用法（输出到 input_translated.srt）
python main.py your_subtitle.srt

# 指定输出文件
python main.py your_subtitle.srt -o output.srt

# 指定目标语言（覆盖 .env 配置）
python main.py your_subtitle.srt -l Japanese

# 指定批次大小（覆盖 .env 配置）
python main.py your_subtitle.srt -b 50

# 忽略之前的进度，从头开始
python main.py your_subtitle.srt --no-resume
```

### 命令行参数

| 参数 | 简写 | 说明 |
|------|------|------|
| `input` | - | 输入的 .srt 文件路径 |
| `--output` | `-o` | 输出文件路径（默认：`input_translated.srt`）|
| `--lang` | `-l` | 目标语言（覆盖 .env 配置）|
| `--batch` | `-b` | 批次大小（覆盖 .env 配置）|
| `--test` | - | 测试 API 连接 |
| `--no-resume` | - | 忽略之前的进度，从头开始翻译 |

## 断点续传

程序会自动保存翻译进度：

1. **自动保存**：每翻译完一个批次，自动保存进度到 `.progress` 文件
2. **中断恢复**：
   - API 错误重试 3 次失败后，自动保存进度并退出
   - 按 `Ctrl+C` 手动中断时，自动保存进度
3. **继续翻译**：再次运行相同命令，程序会询问是否继续

```
📂 Found previous progress: 50/200 subtitles translated.
   Continue from where you left off? [Y/n]: 
```

## 翻译 Prompt 设计

程序使用专门针对字幕翻译优化的 Prompt：

- **批量处理**：将多条字幕编号后一起发送，保持上下文连贯
- **换行保持**：使用 `[BR]` 占位符处理字幕内换行
- **角色设定**：设定为专业影视翻译专家
- **格式约束**：要求返回相同数量的编号行，确保一一对应

## 项目结构

```
subtitle/
├── main.py           # 命令行入口
├── translator.py     # 核心翻译逻辑
├── requirements.txt  # Python 依赖
├── .env             # 环境配置（需自行创建）
├── .env.example     # 配置模板
└── README.md        # 本文档
```

## 故障排除

### Connection error

如果遇到 `Connection error`，可能是因为：

1. **代理问题**：本地 API 不需要代理，确保 `.env` 中设置 `DISABLE_PROXY=true`
2. **API 地址错误**：检查 `OPENAI_BASE_URL` 是否正确（注意是否需要 `/v1` 后缀）
3. **服务未启动**：确保本地 API 服务已启动

使用 curl 测试 API：
```bash
curl http://127.0.0.1:8045/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model": "your-model", "messages": [{"role": "user", "content": "Hello"}]}'
```

### 429 Too Many Requests（限流）

1. 增加 `REQUEST_INTERVAL`（如设为 `2.0`）
2. 减少 `BATCH_SIZE`（如设为 `20`）
3. 程序会自动重试 3 次，每次等待 3 秒

## License

MIT
