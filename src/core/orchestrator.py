"""编排引擎：系统的大脑，决定谁在什么时候、收到什么输入、是否必须回复。

职责：解析 @mention、划分 must_reply / may_reply、按 Turn 执行 Agent 调用、
保存消息并推送 WebSocket，必要时链式触发下一轮 Turn。

记忆写入：从 Agent 输出中解析两种标记并写入对应存储：
  <!--MEMORY:{"type":"decision","content":"...","importance":0.9}-->
      → 写入 MemoryStore（群聊共享，所有成员可见）
  <!--PERSONAL_LOG:内容-->
      → 写入 workspaces/{agent_id}/memory/{today}.md（个人日志）
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.core.call_logger import CallLogger
from src.models.protocol import AgentOutput
from src.models.session import GroupConfig

if TYPE_CHECKING:
    from src.api.websocket import WebSocketManager
    from src.core.context_builder import ContextBuilder
    from src.core.session_manager import SessionManager
    from src.memory.personal import PersonalMemoryManager
    from src.memory.session_summary import SessionSummaryManager
    from src.memory.store import MemoryStore
    from src.registry.agent_registry import AgentRegistry
    from src.worker.runtime import WorkerRuntime

logger = logging.getLogger(__name__)

# 记忆标记正则
_RE_MEMORY = re.compile(r"<!--MEMORY:(\{.*?\})-->", re.DOTALL)
_RE_PERSONAL_LOG = re.compile(r"<!--PERSONAL_LOG:(.*?)-->", re.DOTALL)


@dataclass
class Turn:
    """一个回合：由一条消息触发，包含必须回复与可选回复的 Agent 列表及执行参数。"""

    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_message_id: str | None = None
    trigger_source: str = ""  # 触发者：user_id 或 agent_id

    must_reply_agents: list[str] = field(default_factory=list)
    may_reply_agents: list[str] = field(default_factory=list)
    completed_replies: list[AgentOutput] = field(default_factory=list)

    group_agent_ids: list[str] = field(default_factory=list)

    max_responders: int = 5
    timeout_seconds: int = 120
    chain_depth: int = 0


class Orchestrator:
    """编排引擎：根据新消息与 @mention 创建 Turn，依次执行 must_reply / may_reply 并处理链式回复。"""

    def __init__(
        self,
        session_manager: SessionManager,
        context_builder: ContextBuilder,
        worker_runtime: WorkerRuntime,
        registry: AgentRegistry,
        ws_manager: WebSocketManager | None = None,
        default_config: GroupConfig | None = None,
        memory_store: MemoryStore | None = None,
        personal_memory: PersonalMemoryManager | None = None,
        session_summary: SessionSummaryManager | None = None,
        call_logger: CallLogger | None = None,
        conversation_managers: dict[str, Any] | None = None,  # group_id -> ConversationManager
    ):
        self.session_manager = session_manager
        self.context_builder = context_builder
        self.worker_runtime = worker_runtime
        self.registry = registry
        self.ws_manager = ws_manager
        self.config = default_config or GroupConfig()
        self.memory_store = memory_store
        self.personal_memory = personal_memory
        self.session_summary = session_summary
        self.call_logger = call_logger
        self.conversation_managers = conversation_managers or {}  # Lazy: create on demand

    def _get_conversation_manager(self, agent_id: str) -> Any:
        """为特定 Agent 获取或创建 ConversationManager。"""
        from src.core.conversation_manager import ConversationManager

        profile = self.registry.get_agent(agent_id)
        if not profile:
            return None

        if agent_id not in self.conversation_managers:
            self.conversation_managers[agent_id] = ConversationManager(profile.workspace_dir)

        return self.conversation_managers[agent_id]

    async def _save_user_message_to_conversations(self, group_id: str, message: Any) -> None:
        """将用户消息保存到所有 Agent 的对话文件中。"""
        for agent_id in self.registry.agents.keys():
            try:
                conv_mgr = self._get_conversation_manager(agent_id)
                if conv_mgr:
                    conv_mgr.append_message(group_id, message)
                    logger.debug(f"Saved user message to {agent_id}'s conversations/{group_id}.md")
            except Exception as e:
                logger.warning(f"Failed to save message to {agent_id}'s conversations: {e}")

    async def _save_agent_response_to_conversation(self, agent_id: str, group_id: str, content: str) -> None:
        """将 Agent 的响应保存到所有 Agent 的对话文件中（所有人都能看到）。"""
        from src.models.protocol import Message
        from datetime import datetime

        profile = self.registry.get_agent(agent_id)
        msg = Message(
            author_id=agent_id,
            author_name=profile.name if profile else agent_id,
            content=content,
            role="assistant",
            timestamp=datetime.now(),
        )

        # 保存到所有 Agent 的对话文件
        for other_agent_id in self.registry.agents.keys():
            try:
                conv_mgr = self._get_conversation_manager(other_agent_id)
                if conv_mgr:
                    conv_mgr.append_message(group_id, msg)
                    logger.debug(f"Saved agent {agent_id}'s response to {other_agent_id}'s conversations/{group_id}.md")
            except Exception as e:
                logger.warning(f"Failed to save agent response to {other_agent_id}'s conversations: {e}")

    async def on_new_message(
        self,
        group_id: str,
        message_content: str,
        author_id: str,
        mentions: list[str] | None = None,
    ) -> None:
        """处理新消息：查群组与成员、解析 @mention、划分 must/may_reply，创建并执行 Turn。"""
        logger.info(
            "[CALL] on_new_message: group_id=%s author_id=%s content_len=%d content_preview=%s",
            group_id, author_id, len(message_content),
            (message_content[:80] + "…") if len(message_content) > 80 else message_content,
        )

        # 保存用户消息到所有 Agent 的对话文件
        try:
            from src.models.protocol import Message
            from datetime import datetime

            user_msg = Message(
                author_id=author_id,
                author_name=author_id,  # TODO: 可从前端获取
                content=message_content,
                role="user",
                timestamp=datetime.now(),
            )
            await self._save_user_message_to_conversations(group_id, user_msg)
        except Exception as e:
            logger.warning(f"Failed to save user message to conversations: {e}")

        group = await self.session_manager.get_group(group_id)
        if not group:
            logger.error("[CALL] Group not found: group_id=%s", group_id)
            return
        config = group.config

        agent_members = [m.agent_id for m in group.members if m.type == "agent" and m.agent_id]
        logger.info("[CALL] Group resolved: agent_members=%s", agent_members)

        parsed_mentions = mentions or self._parse_mentions(message_content, agent_members)
        logger.info(
            "[CALL] Mention resolution: frontend_mentions=%s parsed_mentions=%s",
            mentions, parsed_mentions,
        )

        must_reply: list[str] = []
        may_reply: list[str] = []
        if "@all" in parsed_mentions or "@所有人" in parsed_mentions:
            must_reply = list(agent_members)
            logger.info("[CALL] @all/所有人 → must_reply = all agents: %s", must_reply)
        else:
            must_reply = [m for m in parsed_mentions if m in agent_members]
            may_reply = [m for m in agent_members if m not in must_reply]
            logger.info("[CALL] Judged: must_reply=%s may_reply=%s", must_reply, may_reply)

        if not must_reply and not may_reply:
            may_reply = list(agent_members)
            logger.info("[CALL] No mentions → all as may_reply: %s", may_reply)

        turn = Turn(
            trigger_source=author_id,
            must_reply_agents=must_reply,
            may_reply_agents=may_reply,
            group_agent_ids=agent_members,
            max_responders=config.max_responders,
            timeout_seconds=config.turn_timeout_seconds,
            chain_depth=0,
        )
        logger.info(
            "[CALL] Turn created: turn_id=%s trigger_source=%s must_reply_agents=%s "
            "may_reply_agents=%s max_responders=%s",
            turn.turn_id, turn.trigger_source, turn.must_reply_agents,
            turn.may_reply_agents, turn.max_responders,
        )

        await self.execute_turn(turn, group_id, config)

    async def execute_turn(self, turn: Turn, group_id: str, config: GroupConfig) -> None:
        """执行一个完整回合：串行执行以保证上下文实时更新。"""
        logger.info(
            "[CALL] execute_turn: turn_id=%s group_id=%s chain_depth=%s",
            turn.turn_id, group_id, turn.chain_depth,
        )
        all_next_mentions: set[str] = set()
        replied_agents: set[str] = set()

        # Phase A：must_reply（被 @ 的）
        # 改为串行执行，确保后一个被 @ 的人能看到前一个人的回复
        for agent_id in turn.must_reply_agents:
            logger.info("[CALL] Phase A (must_reply) invoke: agent=%s", agent_id)
            try:
                result = await self._invoke_one(agent_id, group_id, "must_reply", turn)
                output: AgentOutput = result
                output = await self._process_memory_markers(output, agent_id, group_id)
                
                # 立即保存并广播，这样下一个 Agent 就能看到这条消息
                await self._save_call_log_and_broadcast(output, agent_id, group_id, turn.turn_id)
                await self.session_manager.save_message(
                    group_id=group_id,
                    author_id=agent_id,
                    content=output.content,
                    author_type="agent",
                    author_name=self.registry.get_agent(agent_id).name,
                    turn_id=turn.turn_id,
                    metadata={"next_mentions": output.next_mentions},
                )
                # 保存到对话文件
                await self._save_agent_response_to_conversation(agent_id, group_id, output.content)
                if self.ws_manager:
                    await self.ws_manager.broadcast_message(group_id, {
                        "type": "agent_message",
                        "agent_id": agent_id,
                        "content": output.content,
                        "turn_id": turn.turn_id,
                    })
                all_next_mentions.update(output.next_mentions)
                replied_agents.add(agent_id)
            except Exception as e:
                logger.error("[CALL] Agent %s failed: %s", agent_id, e, exc_info=True)
                await self._save_error_log(agent_id, group_id, turn.turn_id, str(e))
                # 广播错误通知，避免用户误以为系统正常运行
                profile = self.registry.get_agent(agent_id)
                agent_name = profile.name if profile else agent_id
                error_content = f"⚠️ [{agent_name}] 调用失败：{str(e)}"
                if self.ws_manager:
                    await self.ws_manager.broadcast_message(group_id, {
                        "type": "system_message",
                        "content": error_content,
                    })
                await self.session_manager.save_message(
                    group_id=group_id,
                    author_id="system",
                    content=error_content,
                    author_type="system",
                    author_name="System",
                    turn_id=turn.turn_id,
                )

        # Phase B：may_reply（可选）
        # 同样改为串行，避免多人同时抢答导致的上下文错乱
        remaining = turn.max_responders - len(replied_agents)
        if remaining > 0 and turn.may_reply_agents:
            potential_may_agents = [aid for aid in turn.may_reply_agents if aid not in replied_agents]
            
            for agent_id in potential_may_agents:
                if len(replied_agents) >= turn.max_responders:
                    break
                
                logger.info("[CALL] Phase B (may_reply) invoke: agent=%s", agent_id)
                try:
                    result = await self._invoke_one(agent_id, group_id, "may_reply", turn)
                    output: AgentOutput = result
                    if not output.should_respond:
                        continue
                        
                    output = await self._process_memory_markers(output, agent_id, group_id)
                    await self._save_call_log_and_broadcast(output, agent_id, group_id, turn.turn_id)
                    await self.session_manager.save_message(
                        group_id=group_id,
                        author_id=agent_id,
                        content=output.content,
                        author_type="agent",
                        author_name=self.registry.get_agent(agent_id).name,
                        turn_id=turn.turn_id,
                        metadata={"next_mentions": output.next_mentions},
                    )
                    # 保存到对话文件
                    await self._save_agent_response_to_conversation(agent_id, group_id, output.content)
                    if self.ws_manager:
                        await self.ws_manager.broadcast_message(group_id, {
                            "type": "agent_message",
                            "agent_id": agent_id,
                            "content": output.content,
                            "turn_id": turn.turn_id,
                        })
                    all_next_mentions.update(output.next_mentions)
                    replied_agents.add(agent_id)
                except Exception as e:
                    logger.error("[CALL] Agent %s (may_reply) failed: %s", agent_id, e, exc_info=True)
                    await self._save_error_log(agent_id, group_id, turn.turn_id, str(e))
                    profile = self.registry.get_agent(agent_id)
                    agent_name = profile.name if profile else agent_id
                    error_content = f"⚠️ [{agent_name}] 调用失败：{str(e)}"
                    if self.ws_manager:
                        await self.ws_manager.broadcast_message(group_id, {
                            "type": "system_message",
                            "content": error_content,
                        })
                    await self.session_manager.save_message(
                        group_id=group_id,
                        author_id="system",
                        content=error_content,
                        author_type="system",
                        author_name="System",
                        turn_id=turn.turn_id,
                    )

        # 根据 next_mentions 与链深度决定是否再开一轮 Turn
        # 修复：不再强制减去 replied_agents。
        # 只要有显式的 next_mentions，就应该允许在下一层 chain_depth 中继续触发，
        # 即使该 Agent 在当前层已经回复过（这对于接龙、AB 对话至关重要）。
        # 安全性由 chain_depth_limit 保证。

        if all_next_mentions and turn.chain_depth < config.chain_depth_limit:
            # 使用初始快照成员列表，不重拉 DB，防止竞态条件引入新加入的成员
            agent_members = turn.group_agent_ids
            # 过滤：只触发实际在群里的成员，防止 next_mentions 触发非群成员
            valid_next_mentions = [a for a in all_next_mentions if a in agent_members]
            remaining_agents = [a for a in agent_members if a not in valid_next_mentions and a not in replied_agents]

            if not valid_next_mentions:
                logger.warning("[CALL] next_mentions %s 全部不在群成员列表中，跳过链式触发", all_next_mentions)
            else:
                if len(valid_next_mentions) < len(all_next_mentions):
                    skipped = [a for a in all_next_mentions if a not in agent_members]
                    logger.warning("[CALL] next_mentions 过滤掉非群成员: %s", skipped)
                next_turn = Turn(
                    trigger_source="system",
                    must_reply_agents=valid_next_mentions,
                    may_reply_agents=remaining_agents,
                    group_agent_ids=agent_members,
                    max_responders=config.max_responders,
                    timeout_seconds=config.turn_timeout_seconds,
                    chain_depth=turn.chain_depth + 1,
                )
                await self.execute_turn(next_turn, group_id, config)
        elif turn.chain_depth >= config.chain_depth_limit:
            if self.ws_manager:
                await self.ws_manager.broadcast_message(group_id, {
                    "type": "system_message",
                    "content": f"自动对话已达到 {config.chain_depth_limit} 轮上限，等待人类指令。",
                })

    async def _process_memory_markers(
        self, output: AgentOutput, agent_id: str, group_id: str
    ) -> AgentOutput:
        """从 Agent 输出中提取记忆标记，写入存储，并从展示内容中清除标记。

        支持两种标记：
          <!--MEMORY:{"type":"...","content":"...","importance":0.8}-->
              写入群聊 MemoryStore（所有成员共享）
          <!--PERSONAL_LOG:内容-->
              写入 workspaces/{agent_id}/memory/{today}.md（个人日志）
        """
        content = output.content
        session_memories: list[dict] = []
        personal_logs: list[str] = []

        # 提取 MEMORY 标记
        for match in _RE_MEMORY.finditer(content):
            try:
                data = json.loads(match.group(1))
                session_memories.append(data)
            except json.JSONDecodeError:
                logger.warning(
                    "[MEMORY] Invalid JSON in MEMORY marker from agent=%s: %s",
                    agent_id, match.group(1)[:100],
                )

        # 提取 PERSONAL_LOG 标记
        for match in _RE_PERSONAL_LOG.finditer(content):
            log_content = match.group(1).strip()
            if log_content:
                personal_logs.append(log_content)

        # 清理标记（无论是否解析成功都从展示内容里去掉）
        content = _RE_MEMORY.sub("", content)
        content = _RE_PERSONAL_LOG.sub("", content).strip()
        output.content = content

        # 写入群聊 MemoryStore
        if session_memories and self.memory_store:
            from src.memory.store import MemoryEntry
            for mem in session_memories:
                mem_content = mem.get("content", "").strip()
                if not mem_content:
                    continue
                entry = MemoryEntry(
                    session_id=group_id,
                    content=mem_content,
                    memory_type=mem.get("type", "summary"),
                    importance=float(mem.get("importance", 0.7)),
                    source_message_id=agent_id,
                )
                await self.memory_store.save_memory(group_id, entry)
                logger.info(
                    "[MEMORY] Saved session memory: agent=%s type=%s content_preview=%s",
                    agent_id, entry.memory_type, mem_content[:80],
                )
            # 重建滚动摘要
            if self.session_summary:
                all_entries = await self.memory_store.get_all_memories(group_id)
                self.session_summary.rebuild_from_entries(group_id, all_entries)

        # 写入个人日志
        if personal_logs and self.personal_memory:
            profile = self.registry.get_agent(agent_id)
            if profile and profile.workspace_dir:
                for log in personal_logs:
                    self.personal_memory.append_daily_log(profile.workspace_dir, log)
                    logger.info(
                        "[MEMORY] Saved personal log: agent=%s content_preview=%s",
                        agent_id, log[:80],
                    )

        return output

    async def _invoke_one(
        self, agent_id: str, group_id: str, invocation: str, turn: Turn
    ) -> AgentOutput:
        """调用单个 Agent：先构建 AgentInput，再通过 worker_runtime 执行，带超时。"""
        logger.info(
            "[CALL] _invoke_one: agent_id=%s group_id=%s invocation=%s turn_id=%s",
            agent_id, group_id, invocation, turn.turn_id,
        )
        agent_input = await self.context_builder.build_input(
            agent_id=agent_id,
            session_id=group_id,
            turn_id=turn.turn_id,
            invocation=invocation,
            mentioned_by=turn.trigger_source,
            group_agent_ids=turn.group_agent_ids,
        )
        logger.info(
            "[CALL] AgentInput built for %s: messages=%d role_prompt_len=%d memory=%s",
            agent_id, len(agent_input.messages),
            len(agent_input.role_prompt or ""),
            "yes" if agent_input.memory_context else "no",
        )
        # 智能选择超时时间：取全局 Turn 超时与该 Agent 自身配置超时的最大值
        profile = self.registry.get_agent(agent_id)
        final_timeout = turn.timeout_seconds
        if profile and profile.cli_config.timeout > final_timeout:
            final_timeout = profile.cli_config.timeout
            logger.info("[CALL] Using agent-specific timeout for %s: %ss", agent_id, final_timeout)

        return await asyncio.wait_for(
            self.worker_runtime.invoke_agent(agent_id, agent_input),
            timeout=final_timeout,
        )

    async def _save_call_log_and_broadcast(
        self,
        output: AgentOutput,
        agent_id: str,
        group_id: str,
        turn_id: str,
    ) -> None:
        """保存调用日志到文件，并通过 WebSocket 广播 turn_log 摘要事件。"""
        from src.core.call_logger import CallLog
        meta = output.execution_meta
        profile = self.registry.get_agent(agent_id)

        if self.call_logger and meta:
            log = CallLog(
                log_id=f"{turn_id}-{agent_id}",
                session_id=group_id,
                turn_id=turn_id,
                agent_id=agent_id,
                agent_name=profile.name if profile else agent_id,
                model_name=meta.model_name,
                prompt_preview=output.prompt_sent or "",
                raw_output_preview=output.raw_output or "",
                content_preview=output.content or "",
                duration_ms=meta.duration_ms,
                cost_usd=meta.cost_usd,
                num_turns=meta.num_turns,
                input_tokens=meta.input_tokens,
                output_tokens=meta.output_tokens,
                tool_calls=[
                    {"name": tc.name, "input": tc.input, "output": tc.output}
                    for tc in meta.tool_calls
                ],
                is_error=meta.is_error,
            )
            self.call_logger.save(log)

        if self.ws_manager and meta:
            await self.ws_manager.broadcast_message(group_id, {
                "type": "turn_log",
                "turn_id": turn_id,
                "agent_id": agent_id,
                "model_name": meta.model_name,
                "duration_ms": meta.duration_ms,
                "cost_usd": meta.cost_usd,
                "num_turns": meta.num_turns,
                "input_tokens": meta.input_tokens,
                "output_tokens": meta.output_tokens,
                "tool_count": len(meta.tool_calls),
                "is_error": meta.is_error,
            })

    async def _save_error_log(self, agent_id: str, group_id: str, turn_id: str, error_msg: str) -> None:
        """当 Agent 调用抛出异常时，向 JSONL 写入一条 is_error=True 的占位记录。"""
        from src.core.call_logger import CallLog
        if not self.call_logger:
            return
        profile = self.registry.get_agent(agent_id)
        log = CallLog(
            log_id=f"{turn_id}-{agent_id}-err",
            session_id=group_id,
            turn_id=turn_id,
            agent_id=agent_id,
            agent_name=profile.name if profile else agent_id,
            raw_output_preview=error_msg,
            content_preview="[AGENT_ERROR]",
            is_error=True,
        )
        self.call_logger.save(log)

    def _parse_mentions(self, content: str, agent_ids: list[str]) -> list[str]:
        """从消息正文解析 @xxx：支持 @all/@所有人、agent_id 或 agent 名称匹配。
        仅当 @ 出现在行首或空白后时才视为提及，避免误伤邮件、文件名等。
        """
        mentions = []
        pattern = r"(?:^|\s)@(\S+)"
        matches = re.findall(pattern, content)
        for match in matches:
            if match in ("all", "所有人"):
                mentions.append("@all")
            elif match in agent_ids:
                mentions.append(match)
            else:
                for aid in agent_ids:
                    profile = self.registry.get_agent(aid)
                    if profile and match == profile.name:
                        mentions.append(aid)
                        break
        return mentions
