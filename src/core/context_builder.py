"""上下文构建器：为每个被唤醒的 Agent 组装 AgentInput。

职责：从 SessionManager 取历史消息、从 MemoryStore 取相关记忆、
从 Registry 取 Agent 配置，拼成一次调用所需的完整输入（含 role_prompt、invocation 等）。
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Literal

from src.models.protocol import AgentInput, Message

if TYPE_CHECKING:
    from src.core.session_manager import SessionManager
    from src.memory.store import MemoryStore
    from src.registry.agent_registry import AgentRegistry


class ContextBuilder:
    """为每个被唤醒的 Agent 组装 AgentInput，控制「能看到什么」与「Token 用量」。"""

    def __init__(
        self,
        session_manager: SessionManager,
        registry: AgentRegistry,
        memory_store: MemoryStore | None = None,
    ):
        """注入会话管理器、Agent 注册表与可选记忆存储。"""
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
        """为指定 Agent 组装一次调用的完整输入：角色、历史、记忆、参数等。"""
        # 从注册表取该 Agent 的配置（角色提示、最大 token 等）
        profile = self.registry.get_agent(agent_id)

        # 从会话中取最近 N 条消息并转为 protocol.Message，用于对话上下文
        messages = await self._get_truncated_history(
            session_id,
            max_messages=50,  # MVP：简单按条数截断
        )

        # 若有记忆存储，用最近一条消息做查询，取相关记忆片段拼成字符串
        memory_context = None
        if self.memory_store:
            memory_context = await self._retrieve_memory(session_id, messages)

        # 拼成 AgentInput 返回给编排器调用
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
        """获取该会话最近 max_messages 条消息，并转为 protocol.Message 列表。"""
        stored_messages = await self.session_manager.get_messages(
            session_id, limit=max_messages
        )
        return [
            self.session_manager.stored_to_protocol(m) for m in stored_messages
        ]

    async def _retrieve_memory(
        self, session_id: str, messages: list[Message]
    ) -> str | None:
        """用最近一条消息内容在记忆库中检索，返回 top_k 条拼成的字符串；无记忆则返回 None。"""
        if not self.memory_store or not messages:
            return None
        query = messages[-1].content
        entries = await self.memory_store.search_memory(session_id, query, top_k=5)
        if not entries:
            return None
        return "\n---\n".join(e.content for e in entries)
