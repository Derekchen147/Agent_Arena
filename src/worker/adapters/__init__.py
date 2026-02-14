"""CLI 适配器：BaseAdapter 抽象基类，ClaudeCliAdapter / GenericCliAdapter 实现。"""
from src.worker.adapters.base import BaseAdapter
from src.worker.adapters.claude_cli import ClaudeCliAdapter
from src.worker.adapters.generic_cli import GenericCliAdapter

__all__ = [
    "BaseAdapter",
    "ClaudeCliAdapter",
    "GenericCliAdapter",
]
