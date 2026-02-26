"""上下文构建器：为每个被唤醒的 Agent 组装 AgentInput。

职责：从 SessionManager 取历史消息、从多层记忆系统取上下文、
从 Registry 取 Agent 配置，拼成一次调用所需的完整输入（含 role_prompt、invocation 等）。

记忆注入优先级（Token 预算由高到低）：
  1. 个人长期记忆  workspaces/{id}/MEMORY.md          (~600 tokens)
  2. 近期工作日志  workspaces/{id}/memory/今天+昨天    (~400 tokens)
  3. 会话滚动摘要  data/memory/summary_{session_id}.md (~300 tokens)
  4. 结构化检索    MemoryStore keyword search top-5    (~200 tokens)
  5. 对话历史      最近 N 条消息（剩余全部 token 预算）
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Literal

from src.models.protocol import AgentInput, Message, Peer

if TYPE_CHECKING:
    from src.core.session_manager import SessionManager
    from src.memory.personal import PersonalMemoryManager
    from src.memory.session_summary import SessionSummaryManager
    from src.memory.store import MemoryStore
    from src.registry.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


class ContextBuilder:
    """为每个被唤醒的 Agent 组装 AgentInput，控制「能看到什么」与「Token 用量」。"""

    def __init__(
        self,
        session_manager: SessionManager,
        registry: AgentRegistry,
        memory_store: MemoryStore | None = None,
        personal_memory: PersonalMemoryManager | None = None,
        session_summary: SessionSummaryManager | None = None,
    ):
        """注入会话管理器、Agent 注册表与可选的记忆组件。"""
        self.session_manager = session_manager
        self.registry = registry
        self.memory_store = memory_store
        self.personal_memory = personal_memory
        self.session_summary = session_summary

    async def build_input(
        self,
        agent_id: str,
        session_id: str,
        turn_id: str,
        invocation: Literal["must_reply", "may_reply"] = "must_reply",
        mentioned_by: str | None = None,
        group_agent_ids: list[str] | None = None,
    ) -> AgentInput:
        """为指定 Agent 组装一次调用的完整输入：角色、历史、记忆、同事列表等。

        Args:
            group_agent_ids: 本群所有 Agent 成员的 agent_id 列表（含自身），
                             用于构建 peers（排除自身后的同事摘要）。
        """
        logger.info(
            "[CALL] context_builder.build_input: agent_id=%s session_id=%s turn_id=%s invocation=%s mentioned_by=%s",
            agent_id, session_id, turn_id, invocation, mentioned_by,
        )

        # 从注册表取该 Agent 的配置（角色提示、最大 token 等）
        profile = self.registry.get_agent(agent_id)

        # 构建同事列表（排除自身）
        peers: list[Peer] = []
        for aid in (group_agent_ids or []):
            if aid == agent_id:
                continue
            peer_profile = self.registry.get_agent(aid)
            if peer_profile:
                peers.append(Peer(
                    agent_id=aid,
                    name=peer_profile.name,
                    skills=peer_profile.skills,
                ))

        # 从会话中取最近 N 条消息并转为 protocol.Message，用于对话上下文
        messages = await self._get_truncated_history(session_id, max_messages=50)
        logger.info(
            "[CALL] context_builder: fetched history messages_count=%s peers_count=%s",
            len(messages), len(peers),
        )

        # 多层记忆上下文组装
        memory_context = await self._build_memory_context(
            agent_id=agent_id,
            workspace_dir=profile.workspace_dir if profile else None,
            session_id=session_id,
            messages=messages,
        )
        logger.info(
            "[CALL] context_builder: memory_context=%s",
            f"{len(memory_context)} chars" if memory_context else "none",
        )

        agent_input = AgentInput(
            session_id=session_id,
            turn_id=turn_id or str(uuid.uuid4()),
            agent_id=agent_id,
            agent_name=profile.name,
            role_prompt=profile.role_prompt,
            invocation=invocation,
            mentioned_by=mentioned_by,
            messages=messages,
            peers=peers,
            memory_context=memory_context,
            max_output_tokens=profile.max_output_tokens,
            prefer_concise=True,
        )
        logger.info(
            "[CALL] context_builder: AgentInput assembled for %s: session_id=%s turn_id=%s "
            "messages=%d peers=%d role_prompt_len=%d memory_len=%s max_output_tokens=%s",
            agent_id, agent_input.session_id, agent_input.turn_id, agent_input.invocation,
            len(agent_input.messages), len(agent_input.peers),
            len(agent_input.role_prompt or ""),
            len(agent_input.memory_context or ""),
            agent_input.max_output_tokens,
        )
        return agent_input

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    async def _get_truncated_history(
        self, session_id: str, max_messages: int = 50
    ) -> list[Message]:
        """获取该会话最近 max_messages 条消息，并转为 protocol.Message 列表。"""
        stored_messages = await self.session_manager.get_messages(
            session_id, limit=max_messages
        )
        return [self.session_manager.stored_to_protocol(m) for m in stored_messages]

    async def _build_memory_context(
        self,
        agent_id: str,
        workspace_dir: str | None,
        session_id: str,
        messages: list[Message],
    ) -> str | None:
        """多层记忆整合：个人记忆 + 会话摘要 + MemoryStore 检索结果。

        由于群聊只有一个人类用户，无隐私泄漏顾虑，所有层次的记忆都直接注入。
        唯一约束是 Token 预算，各层均设有字符上限。
        """
        parts: list[str] = []

        # ── Layer 1 + 2：个人长期记忆 + 近期日志 ──
        if self.personal_memory and workspace_dir:
            personal_ctx = self.personal_memory.read_context(workspace_dir)
            if personal_ctx:
                parts.append(personal_ctx)

        # ── Layer 3：会话滚动摘要 ──
        if self.session_summary:
            summary = self.session_summary.read_summary(session_id)
            if summary:
                parts.append(f"### 当前会话摘要\n{summary}")

        # ── Layer 4：MemoryStore 结构化检索 ──
        if self.memory_store and messages:
            store_ctx = await self._retrieve_from_store(session_id, messages)
            if store_ctx:
                parts.append(f"### 相关历史记忆\n{store_ctx}")

        return "\n\n---\n\n".join(parts) if parts else None

    async def _retrieve_from_store(
        self, session_id: str, messages: list[Message]
    ) -> str | None:
        """用最近一条消息内容在 MemoryStore 中检索，返回 top_k 条拼成的字符串。"""
        if not self.memory_store or not messages:
            return None
        query = messages[-1].content
        entries = await self.memory_store.search_memory(session_id, query, top_k=5)
        if not entries:
            return None
        return "\n".join(f"- [{e.memory_type}] {e.content}" for e in entries)
