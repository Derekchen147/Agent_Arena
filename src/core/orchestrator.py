"""编排引擎：系统的大脑，决定谁在什么时候、收到什么输入、是否必须回复。

职责：解析 @mention、划分 must_reply / may_reply、按 Turn 执行 Agent 调用、
保存消息并推送 WebSocket，必要时链式触发下一轮 Turn。
"""

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
    """一个回合：由一条消息触发，包含必须回复与可选回复的 Agent 列表及执行参数。"""

    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_message_id: str | None = None
    trigger_source: str = ""  # 触发者：user_id 或 agent_id

    must_reply_agents: list[str] = field(default_factory=list)   # 被 @ 的必须回复
    may_reply_agents: list[str] = field(default_factory=list)   # 可选回复，按名额取
    completed_replies: list[AgentOutput] = field(default_factory=list)

    group_agent_ids: list[str] = field(default_factory=list)  # 本群所有 Agent 成员 ID（含所有 agent）

    max_responders: int = 5   # 本回合最多允许多少个 Agent 回复
    timeout_seconds: int = 120
    chain_depth: int = 0      # 当前链式深度，用于限制自动多轮


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
        """处理新消息：查群组与成员、解析 @mention、划分 must/may_reply，创建并执行 Turn。"""
        logger.info(
            "[CALL] on_new_message: group_id=%s author_id=%s content_len=%d content_preview=%s",
            group_id, author_id, len(message_content),
            (message_content[:80] + "…") if len(message_content) > 80 else message_content,
        )
        # 获取群组及其配置，用于本回合超时、人数上限等
        group = await self.session_manager.get_group(group_id)
        if not group:
            logger.error("[CALL] Group not found: group_id=%s", group_id)
            return
        config = group.config

        # 收集该群内所有 Agent 成员 ID，用于后续划分回复名单
        agent_members = [m.agent_id for m in group.members if m.type == "agent" and m.agent_id]
        logger.info(
            "[CALL] Group resolved: agent_members=%s",
            agent_members,
        )

        # 若前端未传 mentions，则从消息正文解析 @xxx
        parsed_mentions = mentions or self._parse_mentions(message_content, agent_members)
        logger.info(
            "[CALL] Mention resolution: frontend_mentions=%s parsed_mentions=%s (from content)",
            mentions,
            parsed_mentions,
        )

        # 根据 @ 结果划分：被 @ 的为 must_reply，其余为 may_reply；@all 则全员 must
        must_reply: list[str] = []
        may_reply: list[str] = []
        if "@all" in parsed_mentions or "@所有人" in parsed_mentions:
            must_reply = list(agent_members)
            logger.info("[CALL] @all/所有人 → must_reply = all agents: %s", must_reply)
        else:
            must_reply = [m for m in parsed_mentions if m in agent_members]
            may_reply = [m for m in agent_members if m not in must_reply]
            logger.info(
                "[CALL] Judged: must_reply=%s may_reply=%s",
                must_reply,
                may_reply,
            )
        if not must_reply and not may_reply:
            # 没有任何 @ 时，所有 Agent 都作为可选回复
            may_reply = list(agent_members)
            logger.info("[CALL] No mentions → all as may_reply: %s", may_reply)

        # 构造本回合并交给执行器
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
            "[CALL] Turn created: turn_id=%s trigger_source=%s must_reply_agents=%s may_reply_agents=%s max_responders=%s",
            turn.turn_id,
            turn.trigger_source,
            turn.must_reply_agents,
            turn.may_reply_agents,
            turn.max_responders,
        )

        await self.execute_turn(turn, group_id, config)

    async def execute_turn(self, turn: Turn, group_id: str, config: GroupConfig) -> None:
        """执行一个完整回合：先并行执行 must_reply，再并行执行 may_reply（按名额），最后处理链式 @。"""
        logger.info(
            "[CALL] execute_turn: turn_id=%s group_id=%s chain_depth=%s",
            turn.turn_id,
            group_id,
            turn.chain_depth,
        )
        all_next_mentions: set[str] = set()   # 本回合内所有 Agent 输出的 next_mentions 并集
        replied_agents: set[str] = set()      # 本回合已回复的 Agent，避免重复

        # Phase A：被 @ 的 Agent 必须回复，并行调用
        if turn.must_reply_agents:
            logger.info(
                "[CALL] Phase A (must_reply) start: agents=%s",
                turn.must_reply_agents,
            )
            must_tasks = [
                self._invoke_one(agent_id, group_id, "must_reply", turn)
                for agent_id in turn.must_reply_agents
            ]
            must_results = await asyncio.gather(*must_tasks, return_exceptions=True)

            for agent_id, result in zip(turn.must_reply_agents, must_results):
                if isinstance(result, Exception):
                    logger.error(
                        "[CALL] Agent %s failed: %s",
                        agent_id,
                        result,
                        exc_info=True,
                    )
                    continue
                output: AgentOutput = result
                # 将 Agent 回复落库并写入 turn_id、next_mentions
                await self.session_manager.save_message(
                    group_id=group_id,
                    author_id=agent_id,
                    content=output.content,
                    author_type="agent",
                    author_name=self.registry.get_agent(agent_id).name,
                    turn_id=turn.turn_id,
                    metadata={"next_mentions": output.next_mentions},
                )
                # 通过 WebSocket 推送给该群所有连接中的前端
                if self.ws_manager:
                    await self.ws_manager.broadcast_message(group_id, {
                        "type": "agent_message",
                        "agent_id": agent_id,
                        "content": output.content,
                        "turn_id": turn.turn_id,
                    })
                all_next_mentions.update(output.next_mentions)
                replied_agents.add(agent_id)
            logger.info(
                "[CALL] Phase A (must_reply) done: replied=%s next_mentions=%s",
                list(replied_agents),
                list(all_next_mentions),
            )

        # Phase B：可选回复的 Agent，在剩余名额内并行调用；仅当 should_respond 为 True 时落库与推送
        remaining = turn.max_responders - len(replied_agents)
        if remaining > 0 and turn.may_reply_agents:
            may_agents = [
                aid for aid in turn.may_reply_agents
                if aid not in replied_agents
            ][:remaining]
            logger.info(
                "[CALL] Phase B (may_reply) start: remaining_slots=%s may_agents=%s",
                remaining,
                may_agents,
            )

            may_tasks = [
                self._invoke_one(agent_id, group_id, "may_reply", turn)
                for agent_id in may_agents
            ]
            may_results = await asyncio.gather(*may_tasks, return_exceptions=True)

            for agent_id, result in zip(may_agents, may_results):
                if isinstance(result, Exception):
                    logger.error(
                        "[CALL] Agent %s (may_reply) failed: %s",
                        agent_id,
                        result,
                        exc_info=True,
                    )
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

        # 根据 next_mentions 与链深度决定是否再开一轮 Turn
        if not config.re_invoke_already_replied:
            all_next_mentions -= replied_agents  # 本回合已回复的不再被链式召唤

        if all_next_mentions and turn.chain_depth < config.chain_depth_limit:
            # 用 next_mentions 作为下一回合 must_reply，其余作为 may_reply，深度 +1
            group = await self.session_manager.get_group(group_id)
            agent_members = [m.agent_id for m in group.members if m.type == "agent" and m.agent_id]
            remaining_agents = [a for a in agent_members if a not in all_next_mentions and a not in replied_agents]

            next_turn = Turn(
                trigger_source="system",
                must_reply_agents=list(all_next_mentions),
                may_reply_agents=remaining_agents,
                group_agent_ids=agent_members,
                max_responders=config.max_responders,
                timeout_seconds=config.turn_timeout_seconds,
                chain_depth=turn.chain_depth + 1,
            )
            await self.execute_turn(next_turn, group_id, config)
        elif turn.chain_depth >= config.chain_depth_limit:
            # 达到链深度上限时提示前端，停止自动继续
            if self.ws_manager:
                await self.ws_manager.broadcast_message(group_id, {
                    "type": "system_message",
                    "content": f"自动对话已达到 {config.chain_depth_limit} 轮上限，等待人类指令。",
                })

    async def _invoke_one(
        self, agent_id: str, group_id: str, invocation: str, turn: Turn
    ) -> AgentOutput:
        """调用单个 Agent：先构建 AgentInput，再通过 worker_runtime 执行，带超时。"""
        logger.info(
            "[CALL] _invoke_one: agent_id=%s group_id=%s invocation=%s turn_id=%s",
            agent_id,
            group_id,
            invocation,
            turn.turn_id,
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
            agent_id,
            len(agent_input.messages),
            len(agent_input.role_prompt or ""),
            "yes" if agent_input.memory_context else "no",
        )
        return await asyncio.wait_for(
            self.worker_runtime.invoke_agent(agent_id, agent_input),
            timeout=turn.timeout_seconds,
        )

    def _parse_mentions(self, content: str, agent_ids: list[str]) -> list[str]:
        """从消息正文解析 @xxx：支持 @all/@所有人、agent_id 或 agent 名称匹配。
        仅当 @ 出现在行首或空白后时才视为提及，避免误伤邮件、文件名等（如 user@example.com、@file.txt）。
        """
        mentions = []
        # 仅匹配「行首或空白后的 @xxx」，避免把 user@example.com、@orchestrator.py 等当提及
        pattern = r"(?:^|\s)@(\S+)"
        matches = re.findall(pattern, content)
        for match in matches:
            if match in ("all", "所有人"):
                mentions.append("@all")
            elif match in agent_ids:
                mentions.append(match)
            else:
                # 按显示名称匹配：若某 Agent 的 name 等于 match 则加入
                for aid in agent_ids:
                    profile = self.registry.get_agent(aid)
                    if profile and match == profile.name:
                        mentions.append(aid)
                        break
        return mentions
