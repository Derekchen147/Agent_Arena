"""WorkerRuntime：管理每个 Agent 的 CLI 调用，在 Agent 的工作目录中执行。"""

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
    """管理所有 Agent 的 CLI 调用。

    每次调用时根据 Agent 的 cli_config 选择对应的 Adapter，
    并在 Agent 的 workspace_dir 中执行。
    """

    def __init__(
        self,
        registry: AgentRegistry,
        ws_manager: WebSocketManager | None = None,
    ):
        self.registry = registry
        self.ws_manager = ws_manager

    def _create_adapter(self, cli_type: str, cli_config: dict) -> BaseAdapter:
        """根据 cli_type 创建 Adapter 实例。"""
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
        """调用一个 Agent：在其工作目录中执行 CLI。"""
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
        """清理（CLI 模式下无需持久进程管理）。"""
        pass

    async def _emit_status(self, agent_id: str, status: str, detail: str = "") -> None:
        if self.ws_manager:
            await self.ws_manager.broadcast_status(agent_id, {
                "type": "agent_status",
                "agent_id": agent_id,
                "status": status,
                "detail": detail,
            })
