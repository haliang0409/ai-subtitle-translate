"""
config.py — 配置管理模块
负责读写 config.json，提供默认值填补和最近文件管理。
"""
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG: dict = {
    "apis": [
        {
            "key": "",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "disable_proxy": True,
        }
    ],
    "target_language": "Chinese",
    "model_name": "gpt-4o-mini",
    "batch_size": 30,
    "request_interval": 1.0,
    "context_window": 5,
    "max_retries": 3,
    "retry_delay": 3,
    "disable_proxy": True,
    "theme": "system",
    "recent_files": [],
}


def load() -> dict:
    """读取配置文件，缺失字段用默认值填补。"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = DEFAULT_CONFIG.copy()
            result.update(data)
            return result
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save(data: dict) -> None:
    """将配置字典写入 config.json。"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_recent_file(path: str) -> None:
    """将文件路径插入最近文件列表头部，最多保留 10 条。"""
    data = load()
    recent: list = data.get("recent_files", [])
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    data["recent_files"] = recent[:10]
    save(data)
