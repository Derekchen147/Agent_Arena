"""记忆存储：按会话（群组）存储结构化记忆，供 ContextBuilder 检索注入。

MVP 使用每会话一个 JSON 文件；检索为简单关键词匹配 + importance 加权。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """单条记忆：内容、类型、重要度及来源消息 ID。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    content: str = ""
    memory_type: Literal[
        "decision",      # 关键决策
        "requirement",   # 需求定义
        "task",         # 任务分配
        "issue",        # 问题/Bug
        "summary",      # 阶段摘要
    ] = "summary"
    importance: float = 0.5  # 0.0 ~ 1.0，参与检索排序
    created_at: datetime = Field(default_factory=datetime.now)
    source_message_id: str = ""


class MemoryStore:
    """按 session_id 存储与检索记忆；每个会话对应一个 JSON 文件。"""

    def __init__(self, memory_dir: str = "data/memory"):
        """指定记忆目录，不存在则创建。"""
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_file(self, session_id: str) -> Path:
        """返回该会话对应的 JSON 文件路径。"""
        return self.memory_dir / f"session_{session_id}.json"

    async def save_memory(self, session_id: str, memory: MemoryEntry) -> None:
        """追加一条记忆到该会话文件；先读入现有条目再写回。"""
        memory.session_id = session_id
        file_path = self._get_session_file(session_id)

        entries = await self._load_entries(session_id)
        entries.append(memory)
        self._write_entries(file_path, entries)

    async def search_memory(
        self, session_id: str, query: str, top_k: int = 5
    ) -> list[MemoryEntry]:
        """用 query 分词与各条记忆做关键词重叠 + importance 加权打分，返回 top_k 条。"""
        entries = await self._load_entries(session_id)
        if not entries:
            return []

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
        """返回该会话下全部记忆条目（不排序）。"""
        return await self._load_entries(session_id)

    async def generate_summary(self, session_id: str) -> str:
        """按 importance 取前 10 条记忆，拼成「类型 + 内容」的文本摘要。"""
        entries = await self._load_entries(session_id)
        if not entries:
            return ""
        entries.sort(key=lambda e: e.importance, reverse=True)
        top_entries = entries[:10]
        return "\n".join(f"- [{e.memory_type}] {e.content}" for e in top_entries)

    async def _load_entries(self, session_id: str) -> list[MemoryEntry]:
        """从会话 JSON 文件读取并反序列化为 MemoryEntry 列表；文件不存在返回空列表。"""
        file_path = self._get_session_file(session_id)
        if not file_path.exists():
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [MemoryEntry.model_validate(d) for d in data]

    def _write_entries(self, file_path: Path, entries: list[MemoryEntry]) -> None:
        """将记忆列表序列化为 JSON 写入指定文件。"""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump([e.model_dump(mode="json") for e in entries], f, ensure_ascii=False, indent=2)
