"""Summarizer：摘要生成器，用于压缩历史消息。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.models.protocol import Message

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class Summarizer:
    """摘要生成器。

    MVP 阶段使用简单的消息拼接方式生成摘要。
    后期可替换为调用轻量模型（如 Haiku / GPT-4o-mini）生成高质量摘要。
    """

    async def summarize_messages(self, messages: list[Message]) -> str:
        """将一组消息压缩为摘要。"""
        if not messages:
            return ""

        # MVP: 简单提取每条消息的前 100 字符
        summary_parts = []
        for msg in messages:
            author = msg.author_name or msg.role
            snippet = msg.content[:100] + ("..." if len(msg.content) > 100 else "")
            summary_parts.append(f"- {author}: {snippet}")

        return "## 历史摘要\n" + "\n".join(summary_parts)
