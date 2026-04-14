# -*- coding: utf-8 -*-
"""SimpleMem — Naive RAG baseline for agent memory benchmarks.

说明：
- 为提升 Conda 首次安装可用性，避免在 `import simpleMem_src` 时强制依赖 PyYAML。
- 配置相关对象改为懒加载：仅在真正调用 get_config/reset_config/Config 时才导入。
"""

from .logger import get_logger
from .memory_interface import BaseMemorySystem, Evidence
from .llm_interface import BaseLLMClient, OpenAIClient, get_embedding
from .simple_memory import SimpleRAGMemory


def Config(*args, **kwargs):
    from .config import Config as _Config
    return _Config(*args, **kwargs)


def get_config(*args, **kwargs):
    from .config import get_config as _get_config
    return _get_config(*args, **kwargs)


def reset_config(*args, **kwargs):
    from .config import reset_config as _reset_config
    return _reset_config(*args, **kwargs)

__all__ = [
    "Config",
    "get_config",
    "reset_config",
    "get_logger",
    "BaseMemorySystem",
    "Evidence",
    "BaseLLMClient",
    "OpenAIClient",
    "get_embedding",
    "SimpleRAGMemory",
]
