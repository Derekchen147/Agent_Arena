"""MemoryStore：会话记忆存储，按群组会话存储，不按员工切分。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """一条记忆。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    content: str = ""
    memory_type: Literal[
        "decision",      # 关键决策
        "requirement",   # 需求定义
        "task",          # 任务分配
        "issue",         # 问题/Bug
        "summary",       # 阶段摘要
    ] = "summary"
    importance: float = 0.5  # 0.0 ~ 1.0
    created_at: datetime = Field(default_factory=datetime.now)
    source_message_id: str = ""


class MemoryStore:
    """会话记忆存储。MVP 阶段使用 JSON 文件存储。"""

    def __init__(self, memory_dir: str = "data/memory"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_file(self, session_id: str) -> Path:
        return self.memory_dir / f"session_{session_id}.json"

    async def save_memory(self, session_id: str, memory: MemoryEntry) -> None:
        """保存一条记忆。"""
        memory.session_id = session_id
        file_path = self._get_session_file(session_id)

        entries = await self._load_entries(session_id)
        entries.append(memory)
        self._write_entries(file_path, entries)

    async def search_memory(
        self, session_id: str, query: str, top_k: int = 5
    ) -> list[MemoryEntry]:
        """按关键词检索相关记忆。MVP 阶段使用简单关键词匹配。"""
        entries = await self._load_entries(session_id)
        if not entries:
            return []

        # MVP: 简单关键词匹配 + 按 importance 排序
        query_words = set(query.lower().split())
        scored = []
        for entry in entries:
            content_words = set(entry.content.lower().split())
            overlap = len(query_words & content_words)
            score = overlap * 0.5 + entry.importance * 0.5
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    async def get_all_memories(self, session_id: str) -> list[MemoryEntry]:
        """获取某会话的所有记忆。"""
        return await self._load_entries(session_id)

    async def generate_summary(self, session_id: str) -> str:
        """生成当前会话记忆的摘要。MVP 阶段简单拼接。"""
        entries = await self._load_entries(session_id)
        if not entries:
            return ""
        # 按 importance 排序，取 top 10
        entries.sort(key=lambda e: e.importance, reverse=True)
        top_entries = entries[:10]
        return "\n".join(f"- [{e.memory_type}] {e.content}" for e in top_entries)

    async def _load_entries(self, session_id: str) -> list[MemoryEntry]:
        file_path = self._get_session_file(session_id)
        if not file_path.exists():
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [MemoryEntry.model_validate(d) for d in data]

    def _write_entries(self, file_path: Path, entries: list[MemoryEntry]) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump([e.model_dump(mode="json") for e in entries], f, ensure_ascii=False, indent=2)
