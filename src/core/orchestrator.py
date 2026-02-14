"""编排引擎：系统的大脑，决定谁在什么时候、收到什么输入、是否必须回复。"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.models.protocol import AgentOutput
from src.models.session import GroupConfig

if TYPE_CHECKING:
    from src.api.websocket import WebSocketManager
    from src.core.context_builder import ContextBuilder
    from src.core.session_manager import SessionManager
    from src.registry.agent_registry import AgentRegistry
    from src.worker.runtime import WorkerRuntime

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    """一个回合：一条消息触发，可有多个 Agent 回复。"""

    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_message_id: str | None = None
    trigger_source: str = ""  # 谁发的（user_id 或 agent_id）

    must_reply_agents: list[str] = field(default_factory=list)
    may_reply_agents: list[str] = field(default_factory=list)
    completed_replies: list[AgentOutput] = field(default_factory=list)

    max_responders: int = 5
    timeout_seconds: int = 120
    chain_depth: int = 0


class Orchestrator:
    """编排引擎。"""

    def __init__(
        self,
        session_manager: SessionManager,
        context_builder: ContextBuilder,
        worker_runtime: WorkerRuntime,
        registry: AgentRegistry,
        ws_manager: WebSocketManager | None = None,
        default_config: GroupConfig | None = None,
    ):
        self.session_manager = session_manager
        self.context_builder = context_builder
        self.worker_runtime = worker_runtime
        self.registry = registry
        self.ws_manager = ws_manager
        self.config = default_config or GroupConfig()

    async def on_new_message(
        self,
        group_id: str,
        message_content: str,
        author_id: str,
        mentions: list[str] | None = None,
    ) -> None:
        """处理新消息到达：创建 Turn 并执行。"""
        # 获取群组配置
        group = await self.session_manager.get_group(group_id)
        if not group:
            logger.error(f"Group {group_id} not found")
            return
        config = group.config

        # 获取群组中所有 agent 成员
        agent_members = [m.agent_id for m in group.members if m.type == "agent" and m.agent_id]

        # 解析 @mention
        parsed_mentions = mentions or self._parse_mentions(message_content, agent_members)

        # Step 1 & 2: 确定 must_reply 和 may_reply
        must_reply: list[str] = []
        may_reply: list[str] = []

        if "@all" in parsed_mentions or "@所有人" in parsed_mentions:
            must_reply = list(agent_members)
        else:
            must_reply = [m for m in parsed_mentions if m in agent_members]
            may_reply = [m for m in agent_members if m not in must_reply]

        if not must_reply and not may_reply:
            # 没有 @，所有 agent 都是 may_reply
            may_reply = list(agent_members)

        # 创建 Turn
        turn = Turn(
            trigger_source=author_id,
            must_reply_agents=must_reply,
            may_reply_agents=may_reply,
            max_responders=config.max_responders,
            timeout_seconds=config.turn_timeout_seconds,
            chain_depth=0,
        )

        await self.execute_turn(turn, group_id, config)

    async def execute_turn(self, turn: Turn, group_id: str, config: GroupConfig) -> None:
        """执行一个完整的 Turn。"""
        all_next_mentions: set[str] = set()
        replied_agents: set[str] = set()

        # ── Phase A: must_reply（并行）──
        if turn.must_reply_agents:
            must_tasks = [
                self._invoke_one(agent_id, group_id, "must_reply", turn)
                for agent_id in turn.must_reply_agents
            ]
            must_results = await asyncio.gather(*must_tasks, return_exceptions=True)

            for agent_id, result in zip(turn.must_reply_agents, must_results):
                if isinstance(result, Exception):
                    logger.error(f"Agent {agent_id} failed: {result}")
                    continue
                output: AgentOutput = result
                # 保存消息
                await self.session_manager.save_message(
                    group_id=group_id,
                    author_id=agent_id,
                    content=output.content,
                    author_type="agent",
                    author_name=self.registry.get_agent(agent_id).name,
                    turn_id=turn.turn_id,
                    metadata={"next_mentions": output.next_mentions},
                )
                # 推送到前端
                if self.ws_manager:
                    await self.ws_manager.broadcast_message(group_id, {
                        "type": "agent_message",
                        "agent_id": agent_id,
                        "content": output.content,
                        "turn_id": turn.turn_id,
                    })
                all_next_mentions.update(output.next_mentions)
                replied_agents.add(agent_id)

        # ── Phase B: may_reply（并行）──
        remaining = turn.max_responders - len(replied_agents)
        if remaining > 0 and turn.may_reply_agents:
            may_agents = [
                aid for aid in turn.may_reply_agents
                if aid not in replied_agents
            ][:remaining]

            may_tasks = [
                self._invoke_one(agent_id, group_id, "may_reply", turn)
                for agent_id in may_agents
            ]
            may_results = await asyncio.gather(*may_tasks, return_exceptions=True)

            for agent_id, result in zip(may_agents, may_results):
                if isinstance(result, Exception):
                    logger.error(f"Agent {agent_id} (may_reply) failed: {result}")
                    continue
                output: AgentOutput = result
                if not output.should_respond:
                    continue
                await self.session_manager.save_message(
                    group_id=group_id,
                    author_id=agent_id,
                    content=output.content,
                    author_type="agent",
                    author_name=self.registry.get_agent(agent_id).name,
                    turn_id=turn.turn_id,
                    metadata={"next_mentions": output.next_mentions},
                )
                if self.ws_manager:
                    await self.ws_manager.broadcast_message(group_id, {
                        "type": "agent_message",
                        "agent_id": agent_id,
                        "content": output.content,
                        "turn_id": turn.turn_id,
                    })
                all_next_mentions.update(output.next_mentions)
                replied_agents.add(agent_id)

        # ── 决定是否开启下一个 Turn ──
        if not config.re_invoke_already_replied:
            all_next_mentions -= replied_agents

        if all_next_mentions and turn.chain_depth < config.chain_depth_limit:
            # 获取群组 agent 列表用于 may_reply
            group = await self.session_manager.get_group(group_id)
            agent_members = [m.agent_id for m in group.members if m.type == "agent" and m.agent_id]
            remaining_agents = [a for a in agent_members if a not in all_next_mentions and a not in replied_agents]

            next_turn = Turn(
                trigger_source="system",
                must_reply_agents=list(all_next_mentions),
                may_reply_agents=remaining_agents,
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

    async def _invoke_one(
        self, agent_id: str, group_id: str, invocation: str, turn: Turn
    ) -> AgentOutput:
        """调用单个 Agent。"""
        agent_input = await self.context_builder.build_input(
            agent_id=agent_id,
            session_id=group_id,
            turn_id=turn.turn_id,
            invocation=invocation,
            mentioned_by=turn.trigger_source,
        )
        return await asyncio.wait_for(
            self.worker_runtime.invoke_agent(agent_id, agent_input),
            timeout=turn.timeout_seconds,
        )

    def _parse_mentions(self, content: str, agent_ids: list[str]) -> list[str]:
        """从消息内容中解析 @mention。"""
        mentions = []
        # 匹配 @xxx 模式
        pattern = r"@(\S+)"
        matches = re.findall(pattern, content)
        for match in matches:
            if match in ("all", "所有人"):
                mentions.append("@all")
            elif match in agent_ids:
                mentions.append(match)
            else:
                # 尝试模糊匹配（按 agent name）
                for aid in agent_ids:
                    profile = self.registry.get_agent(aid)
                    if profile and match == profile.name:
                        mentions.append(aid)
                        break
        return mentions
