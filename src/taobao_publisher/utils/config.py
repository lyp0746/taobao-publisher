"""配置管理"""
import json
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
import os

load_dotenv()

CONFIG_FILE = Path("config.json")

_DEFAULT_CONFIG = {
     "ai": {
        # ── 提供商选择 ──────────────────────────────────────
        # 可选: volcano（火山方舟）| openai | custom
        "provider": "volcano",

        # ── 火山方舟（推荐）────────────────────────────────
        # 控制台: https://console.volcengine.com/ark
        "volcano_api_key":  "",   # 填入截图中创建的 API Key
        "volcano_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        # 截图确认 Model ID
        "volcano_model":    "doubao-seed-2-0-pro-260215",
        # 图片生成模型（需要使用支持图片生成的模型）
        "volcano_image_model": "ep-20260305002743-f7pz6",

        # ── OpenAI 兼容 ─────────────────────────────────────
        "openai_api_key":   "",
        "openai_base_url":  "https://api.openai.com/v1",
        "openai_model":     "gpt-4o",

        # ── 自定义 ───────────────────────────────────────────
        "custom_api_key":   "",
        "custom_base_url":  "",
        "custom_model":     "",

        # ── 功能开关 ─────────────────────────────────────────
        "optimize_title":       True,
        "optimize_description": True,
        "optimize_specs":       True,
        "title_style":          "电商爆款风格",
        "description_style":    "专业详细",
    },
    "browser": {
        "headless": os.getenv("BROWSER_HEADLESS", "false").lower() == "true",
        "slow_mo": int(os.getenv("BROWSER_SLOW_MO", "80")),
        "timeout": 30000,
    },
    "publish": {
        "delay_min": int(os.getenv("PUBLISH_DELAY_MIN", "500")),
        "delay_max": int(os.getenv("PUBLISH_DELAY_MAX", "1500")),
        "auto_submit": False,
        "save_draft": True,
        "batch_interval": 3,
    },
    "csv": {
        "last_file": "",
        "encoding": "auto",
    },
}


class Config:
    """配置管理类（单例）"""
    _instance = None
    _data: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """加载配置"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data = self._deep_merge(_DEFAULT_CONFIG.copy(), saved)
            except Exception:
                self._data = _DEFAULT_CONFIG.copy()
        else:
            self._data = _DEFAULT_CONFIG.copy()

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """深度合并配置字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def save(self) -> None:
        """保存配置到文件"""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, *keys: str, default: Any = None) -> Any:
        """获取配置值，支持多级 key"""
        data = self._data
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key, default)
            else:
                return default
        return data

    def set(self, *keys_and_value) -> None:
        """设置配置值，最后一个参数为值"""
        *keys, value = keys_and_value
        data = self._data
        for key in keys[:-1]:
            data = data.setdefault(key, {})
        data[keys[-1]] = value


config = Config()