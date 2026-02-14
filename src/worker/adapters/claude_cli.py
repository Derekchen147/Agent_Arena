"""Claude CLI Adapter：通过 subprocess 调用 Claude Code CLI。

核心逻辑：
- 在 Agent 的 workspace_dir 中启动 claude 命令
- workspace_dir 中的 CLAUDE.md 就是该 Agent 的上下文/角色定义
- Agent 只能看到和修改自己 workspace_dir 下的文件
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Callable

from src.models.protocol import AgentInput, AgentOutput
from src.worker.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


def _subprocess_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    """合并当前进程环境与 extra_env，供子进程使用（如代理）。"""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return env


class ClaudeCliAdapter(BaseAdapter):
    """通过 Claude Code CLI 调用的 Adapter。

    调用方式：claude -p "prompt" --output-format json
    工作目录：Agent 的 workspace_dir
    上下文来源：workspace_dir 中的 CLAUDE.md 和其他文件
    若需代理，在 cli_config.env 中配置 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY，或启动服务前在 shell 中设置。
    """

    def __init__(
        self,
        timeout: int = 300,
        extra_args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.timeout = timeout
        self.extra_args = extra_args or []
        self.env = env or {}

    async def invoke(
        self,
        input: AgentInput,
        workspace_dir: str,
        stream_callback: Callable[[str], None] | None = None,
    ) -> AgentOutput:
        """在 workspace_dir 下执行 claude -p "prompt" --output-format json，解析 JSON 或纯文本为 AgentOutput。"""
        prompt = self._build_prompt(input)

        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        cmd.extend(self.extra_args)

        logger.info(f"Invoking Claude CLI in {workspace_dir} for agent {input.agent_id}")

        run_env = _subprocess_env(self.env)
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace_dir,
                env=run_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            raw_output = stdout.decode("utf-8", errors="replace").strip()
            if process.returncode != 0:
                err = stderr.decode("utf-8", errors="replace").strip()
                logger.error(f"Claude CLI error (code {process.returncode}): {err}")
                return AgentOutput(
                    content=f"[CLI Error] {err or raw_output}",
                    should_respond=True,
                )

            return self._parse_output(raw_output, input)

        except asyncio.TimeoutError:
            logger.error(f"Claude CLI timeout after {self.timeout}s for agent {input.agent_id}")
            return AgentOutput(content="[Timeout] CLI 响应超时", should_respond=True)
        except FileNotFoundError:
            logger.error("Claude CLI not found. Is it installed and on PATH?")
            return AgentOutput(content="[Error] claude 命令未找到，请确认已安装 Claude Code CLI", should_respond=True)

    async def health_check(self, workspace_dir: str) -> bool:
        """执行 claude --version 判断 CLI 是否可用。"""
        run_env = _subprocess_env(self.env)
        try:
            process = await asyncio.create_subprocess_exec(
                "claude", "--version",
                env=run_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=10)
            return process.returncode == 0
        except Exception:
            return False

    def _build_prompt(self, input: AgentInput) -> str:
        """将 AgentInput 转为发给 Claude CLI 的 prompt。

        注意：role_prompt 不在这里注入——它已经写在 workspace_dir/CLAUDE.md 中，
        Claude CLI 会自动读取。这里只构建对话消息。
        """
        parts = []

        # 对话上下文
        if input.messages:
            parts.append("## 当前对话")
            for msg in input.messages:
                author = msg.author_name or msg.role
                parts.append(f"[{author}]: {msg.content}")

        # 记忆注入
        if input.memory_context:
            parts.append(f"\n## 相关记忆\n{input.memory_context}")

        # 响应指引
        if input.invocation == "may_reply":
            parts.append(
                "\n## 注意\n"
                "如果你认为这条消息与你的职责无关，请只回复：SKIP"
            )

        if input.prefer_concise:
            parts.append("\n请简洁回复，突出关键信息。")

        # @mention 协作指引
        parts.append(
            "\n## 协作\n"
            "如果你需要其他同事参与，在回复末尾用这个格式：\n"
            "<!--NEXT_MENTIONS:[\"agent_id_1\",\"agent_id_2\"]-->"
        )

        return "\n".join(parts)

    def _parse_output(self, raw_output: str, input: AgentInput) -> AgentOutput:
        """从 CLI 输出中解析正文：优先 JSON 的 result/content，再处理 SKIP 与 NEXT_MENTIONS。"""
        content = raw_output

        try:
            data = json.loads(raw_output)
            if isinstance(data, dict):
                content = data.get("result", data.get("content", raw_output))
            elif isinstance(data, list):
                text_parts = [
                    block.get("text", "")
                    for block in data
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                content = "\n".join(text_parts) if text_parts else raw_output
        except json.JSONDecodeError:
            content = raw_output

        should_respond = True
        if content.strip() == "SKIP" or content.strip().startswith("SKIP"):
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
