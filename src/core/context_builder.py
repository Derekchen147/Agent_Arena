"""上下文构建器：为每个被唤醒的 Agent 组装 AgentInput。"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Literal

from src.models.protocol import AgentInput, Message

if TYPE_CHECKING:
    from src.core.session_manager import SessionManager
    from src.memory.store import MemoryStore
    from src.registry.agent_registry import AgentRegistry


class ContextBuilder:
    """为每个被唤醒的 Agent 组装 AgentInput。

    核心是控制「它能看到什么」以及「花多少 Token」。
    """

    def __init__(
        self,
        session_manager: SessionManager,
        registry: AgentRegistry,
        memory_store: MemoryStore | None = None,
    ):
        self.session_manager = session_manager
        self.registry = registry
        self.memory_store = memory_store

    async def build_input(
        self,
        agent_id: str,
        session_id: str,
        turn_id: str,
        invocation: Literal["must_reply", "may_reply"] = "must_reply",
        mentioned_by: str | None = None,
    ) -> AgentInput:
        """组装 AgentInput。"""
        # 1. 获取员工 Profile
        profile = self.registry.get_agent(agent_id)

        # 2. 获取消息历史（带截断）
        messages = await self._get_truncated_history(
            session_id,
            max_messages=50,  # MVP: 简单截断最近 50 条
        )

        # 3. 检索相关记忆（按需）
        memory_context = None
        if self.memory_store:
            memory_context = await self._retrieve_memory(session_id, messages)

        # 4. 组装 AgentInput
        return AgentInput(
            session_id=session_id,
            turn_id=turn_id or str(uuid.uuid4()),
            agent_id=agent_id,
            role_prompt=profile.role_prompt,
            invocation=invocation,
            mentioned_by=mentioned_by,
            messages=messages,
            memory_context=memory_context,
            max_output_tokens=profile.max_output_tokens,
            prefer_concise=True,
        )

    async def _get_truncated_history(
        self, session_id: str, max_messages: int = 50
    ) -> list[Message]:
        """获取截断后的消息历史。MVP 阶段只做简单截断。"""
        stored_messages = await self.session_manager.get_messages(
            session_id, limit=max_messages
        )
        return [
            self.session_manager.stored_to_protocol(m) for m in stored_messages
        ]

    async def _retrieve_memory(
        self, session_id: str, messages: list[Message]
    ) -> str | None:
        """检索相关记忆。MVP 阶段暂返回 None。"""
        if not self.memory_store or not messages:
            return None
        # 用最后一条消息作为查询
        query = messages[-1].content
        entries = await self.memory_store.search_memory(session_id, query, top_k=5)
        if not entries:
            return None
        return "\n---\n".join(e.content for e in entries)
