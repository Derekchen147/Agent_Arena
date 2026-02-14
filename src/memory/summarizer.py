"""摘要生成器：将一段历史消息压缩为短文本，用于上下文截断或记忆。

MVP 为简单按条截断前 100 字；后续可改为调用轻量模型生成高质量摘要。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.models.protocol import Message

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class Summarizer:
    """将多条 Message 压缩为一段摘要文本，便于注入到后续上下文中。"""

    async def summarize_messages(self, messages: list[Message]) -> str:
        """对每条消息取作者与内容前 100 字，拼成「## 历史摘要」格式的字符串。"""
        if not messages:
            return ""

        summary_parts = []
        for msg in messages:
            author = msg.author_name or msg.role
            snippet = msg.content[:100] + ("..." if len(msg.content) > 100 else "")
            summary_parts.append(f"- {author}: {snippet}")

        return "## 历史摘要\n" + "\n".join(summary_parts)
