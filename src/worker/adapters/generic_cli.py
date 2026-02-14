"""Generic CLI Adapter：通过 subprocess 调用任意 CLI 工具。

用于接入非 Claude/Cursor 的 CLI 工具，如 Ollama、自定义脚本等。
通过配置指定启动命令，在 Agent 的 workspace_dir 中执行。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Callable

from src.models.protocol import AgentInput, AgentOutput
from src.worker.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class GenericCliAdapter(BaseAdapter):
    """通用 CLI Adapter。

    通过自定义 command 调用任意命令行工具。
    工作目录：Agent 的 workspace_dir。
    """

    def __init__(self, command: str = "", timeout: int = 120, extra_args: list[str] | None = None):
        self.command = command
        self.timeout = timeout
        self.extra_args = extra_args or []

    async def invoke(
        self,
        input: AgentInput,
        workspace_dir: str,
        stream_callback: Callable[[str], None] | None = None,
    ) -> AgentOutput:
        if not self.command:
            return AgentOutput(content="[Error] GenericCliAdapter: command not configured", should_respond=True)

        prompt = self._build_prompt(input)

        try:
            process = await asyncio.create_subprocess_shell(
                self.command,
                cwd=workspace_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt.encode("utf-8")),
                timeout=self.timeout,
            )
            content = stdout.decode("utf-8", errors="replace").strip()
            if not content and stderr:
                content = f"[CLI Error] {stderr.decode('utf-8', errors='replace').strip()}"
        except asyncio.TimeoutError:
            return AgentOutput(content="[Timeout] CLI 响应超时", should_respond=True)
        except Exception as e:
            return AgentOutput(content=f"[CLI Error] {e}", should_respond=True)

        return self._parse_output(content, input)

    async def health_check(self, workspace_dir: str) -> bool:
        return bool(self.command)

    def _build_prompt(self, input: AgentInput) -> str:
        parts = []
        if input.role_prompt:
            parts.append(f"[System] {input.role_prompt}")
        for msg in input.messages:
            parts.append(f"[{msg.author_name or msg.role}] {msg.content}")
        return "\n".join(parts)

    def _parse_output(self, content: str, input: AgentInput) -> AgentOutput:
        should_respond = True
        if content.strip() == "SKIP":
            should_respond = False
            content = ""

        next_mentions = []
        mention_match = re.search(r"<!--NEXT_MENTIONS:(\[.*?\])-->", content)
        if mention_match:
            try:
                next_mentions = json.loads(mention_match.group(1))
            except json.JSONDecodeError:
                pass
            content = re.sub(r"<!--NEXT_MENTIONS:\[.*?\]-->", "", content).strip()

        return AgentOutput(
            content=content,
            next_mentions=next_mentions,
            should_respond=should_respond,
        )
