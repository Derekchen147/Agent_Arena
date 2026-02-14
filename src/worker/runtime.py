"""Worker 运行时：根据 Agent 的 CLI 类型选择适配器，在其工作目录中执行并返回 AgentOutput。

编排器通过 WorkerRuntime.invoke_agent 调用；状态变更可通过 ws_manager 广播给前端。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from src.models.protocol import AgentInput, AgentOutput
from src.worker.adapters.base import BaseAdapter
from src.worker.adapters.claude_cli import ClaudeCliAdapter
from src.worker.adapters.generic_cli import GenericCliAdapter

if TYPE_CHECKING:
    from src.api.websocket import WebSocketManager
    from src.registry.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


class WorkerRuntime:
    """根据 registry 中的 Agent 配置创建对应 Adapter，在 workspace_dir 下执行并返回结果。"""

    def __init__(
        self,
        registry: AgentRegistry,
        ws_manager: WebSocketManager | None = None,
    ):
        """注入注册表与可选的 WebSocket 管理器（用于推送 Agent 状态）。"""
        self.registry = registry
        self.ws_manager = ws_manager

    def _create_adapter(self, cli_type: str, cli_config: dict) -> BaseAdapter:
        """按 cli_type（claude / generic）构造对应的 Adapter，并传入超时与额外参数。"""
        if cli_type == "claude":
            return ClaudeCliAdapter(
                timeout=cli_config.get("timeout", 300),
                extra_args=cli_config.get("extra_args", []),
            )
        elif cli_type == "generic":
            return GenericCliAdapter(
                command=cli_config.get("command", ""),
                timeout=cli_config.get("timeout", 120),
                extra_args=cli_config.get("extra_args", []),
            )
        else:
            raise ValueError(f"Unknown CLI type: {cli_type}")

    async def invoke_agent(
        self,
        agent_id: str,
        input: AgentInput,
        stream_callback: Callable[[str], None] | None = None,
    ) -> AgentOutput:
        """在指定 Agent 的工作目录中执行 CLI：选 Adapter、发状态、调用、返回解析后的 AgentOutput。"""
        profile = self.registry.get_agent(agent_id)
        workspace = Path(profile.workspace_dir).resolve()

        if not workspace.exists():
            logger.error(f"Workspace not found for agent {agent_id}: {workspace}")
            return AgentOutput(
                content=f"[Error] 工作目录不存在: {workspace}",
                should_respond=True,
            )

        adapter = self._create_adapter(
            profile.cli_config.cli_type,
            profile.cli_config.model_dump(),
        )

        try:
            await self._emit_status(agent_id, "analyzing", "正在分析消息...")
            output = await adapter.invoke(input, str(workspace), stream_callback)
            await self._emit_status(agent_id, "done")
            return output
        except Exception as e:
            await self._emit_status(agent_id, "error", str(e))
            raise

    async def shutdown(self) -> None:
        """关闭时清理（当前为 CLI 模式，无持久进程，留空即可）。"""
        pass

    async def _emit_status(self, agent_id: str, status: str, detail: str = "") -> None:
        """向所有 WebSocket 连接广播该 Agent 的状态（供前端展示进度）。"""
        if self.ws_manager:
            await self.ws_manager.broadcast_status(agent_id, {
                "type": "agent_status",
                "agent_id": agent_id,
                "status": status,
                "detail": detail,
            })
