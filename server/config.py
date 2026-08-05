"""共享配置加载器 — 被 main.py 和 chat.py 共用，避免循环导入."""
import os
from pathlib import Path

import yaml

CONFIG_PATH = Path("config/settings.yaml")


def load_config() -> dict:
    """加载 YAML 配置，env var 覆盖."""
    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    for key, env_var in [
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
    ]:
        env_val = os.environ.get(env_var) or os.environ.get(f"AICOMIC_{env_var}")
        if env_val:
            config.setdefault(key, {})["api_key"] = env_val

    return config


def save_config(config: dict):
    """保存 YAML 配置到磁盘."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def build_llm_client(config: dict):
    """构建 LLM 客户端."""
    backend = config.get("backend", "deepseek")
    api_key = config.get(backend, {}).get("api_key", "")
    if not api_key:
        raise RuntimeError(
            f"No API key for backend '{backend}'. "
            f"Set {backend.upper()}_API_KEY env var or config/settings.yaml"
        )

    backend_config = config.get(backend, {})
    if backend == "deepseek":
        from src.aicomic.llm.deepseek import DeepSeekClient
        return DeepSeekClient(
            api_key=api_key,
            model=backend_config.get("model", "deepseek-chat"),
            base_url=backend_config.get("base_url", "https://api.deepseek.com"),
        )
    elif backend == "claude":
        from src.aicomic.llm.claude import ClaudeClient
        return ClaudeClient(
            api_key=api_key,
            model=backend_config.get("model", "claude-sonnet-5-20251001"),
        )
    else:
        raise RuntimeError(f"Unknown backend: {backend}")
