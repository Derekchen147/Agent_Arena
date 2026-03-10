"""CLI 适配器：BaseAdapter 抽象基类，ClaudeCliAdapter / GeminiCliAdapter / CursorCliAdapter / OpencodeCliAdapter 实现。"""
from src.worker.adapters.base import BaseAdapter
from src.worker.adapters.claude_cli import ClaudeCliAdapter
from src.worker.adapters.cursor_cli import CursorCliAdapter
from src.worker.adapters.gemini_cli import GeminiCliAdapter
from src.worker.adapters.generic_cli import GenericCliAdapter
from src.worker.adapters.opencode_cli import OpencodeCliAdapter

__all__ = [
    "BaseAdapter",
    "ClaudeCliAdapter",
    "CursorCliAdapter",
    "GeminiCliAdapter",
    "GenericCliAdapter",
    "OpencodeCliAdapter",
]
