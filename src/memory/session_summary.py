"""群聊会话滚动摘要：从 MemoryStore 条目派生，存为 data/memory/summary_{session_id}.md。

不依赖额外 LLM 调用——直接把 MemoryStore 中的结构化条目按类型汇总成 Markdown，
注入到每次 Agent 调用的上下文中，解决长对话截断后关键信息丢失的问题。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.memory.store import MemoryEntry

logger = logging.getLogger(__name__)

# 摘要中最多展示的条目数（按 importance 排序取 top N）
_SUMMARY_MAX_ENTRIES = 20

_TYPE_LABELS: dict[str, str] = {
    "decision":    "关键决策",
    "requirement": "需求定义",
    "task":        "任务记录",
    "issue":       "问题 / Bug",
    "summary":     "阶段摘要",
}


class SessionSummaryManager:
    """管理每个群聊会话的滚动摘要文件。

    rebuild_from_entries() 在每次有新记忆写入时调用，成本极低（纯文本格式化）。
    read_summary() 供 ContextBuilder 加载，注入到 Agent 调用上下文。
    """

    def __init__(self, memory_dir: str = "data/memory"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _summary_path(self, session_id: str) -> Path:
        return self.memory_dir / f"summary_{session_id}.md"

    def read_summary(self, session_id: str) -> str:
        """读取已生成的会话摘要；文件不存在时返回空字符串。"""
        path = self._summary_path(session_id)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return ""

    def rebuild_from_entries(self, session_id: str, entries: list[MemoryEntry]) -> None:
        """从 MemoryStore 条目重建摘要文件。

        按 importance 降序取前 _SUMMARY_MAX_ENTRIES 条，按 memory_type 分组输出。
        """
        if not entries:
            return

        sorted_entries = sorted(entries, key=lambda e: e.importance, reverse=True)
        top = sorted_entries[:_SUMMARY_MAX_ENTRIES]

        # 按类型分组
        groups: dict[str, list[str]] = {}
        for e in top:
            groups.setdefault(e.memory_type, []).append(e.content)

        lines: list[str] = ["# 当前会话摘要\n"]
        for mtype, label in _TYPE_LABELS.items():
            items = groups.get(mtype, [])
            if items:
                lines.append(f"## {label}")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

        self._summary_path(session_id).write_text("\n".join(lines), encoding="utf-8")
        logger.debug(
            "SessionSummary: rebuilt for session=%s entries=%d", session_id, len(top)
        )
