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
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from src.models.protocol import AgentInput, AgentOutput
from src.worker.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

# 在线程池中执行 subprocess.run，避免 Windows 上 asyncio 默认事件循环不支持子进程
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="claude_cli")


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
        logger.info("[CALL] claude_cli assembled prompt =====> / %s", prompt)

        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        cmd.extend(self.extra_args)
        logger.info(f"[CALL] claude_cli.cmd: cmd: {cmd}")

        logger.info(
            "[CALL] claude_cli.invoke: agent_id=%s workspace_dir=%s prompt_len=%d extra_args=%s",
            input.agent_id,
            workspace_dir,
            len(prompt),
            self.extra_args,
        )
        logger.info("[CALL] claude_cli assembled prompt =====> / %s", prompt)

        run_env = _subprocess_env(self.env)

        def _run_cmd() -> subprocess.CompletedProcess:
            return subprocess.run(
                cmd,
                cwd=workspace_dir,
                env=run_env,
                capture_output=True,
                timeout=self.timeout,
            )

        try:
            loop = asyncio.get_event_loop()
            process = await loop.run_in_executor(_executor, _run_cmd)
            raw_output = (process.stdout or b"").decode("utf-8", errors="replace").strip()
            err = (process.stderr or b"").decode("utf-8", errors="replace").strip()

            if process.returncode != 0:
                logger.error(
                    "[CALL] Claude CLI non-zero exit: agent_id=%s returncode=%s stderr=%s stdout_preview=%s",
                    input.agent_id,
                    process.returncode,
                    err,
                    raw_output[:300] if raw_output else "",
                )
                return AgentOutput(
                    content=f"[CLI Error] {err or raw_output}",
                    should_respond=True,
                )

            logger.info(
                "[CALL] claude_cli: agent_id=%s exit 0 output_len=%d",
                input.agent_id,
                len(raw_output),
            )
            return self._parse_output(raw_output, input)

        except subprocess.TimeoutExpired:
            logger.error(
                "[CALL] Claude CLI timeout: agent_id=%s timeout=%ss",
                input.agent_id,
                self.timeout,
            )
            return AgentOutput(content="[Timeout] CLI 响应超时", should_respond=True)
        except FileNotFoundError:
            logger.error(
                "[CALL] Claude CLI not found (not on PATH). agent_id=%s workspace_dir=%s",
                input.agent_id,
                workspace_dir,
            )
            return AgentOutput(content="[Error] claude 命令未找到，请确认已安装 Claude Code CLI", should_respond=True)
        except Exception as e:
            logger.error(
                "[CALL] claude_cli.invoke exception: agent_id=%s error=%s",
                input.agent_id,
                e,
                exc_info=True,
            )
            raise

    async def health_check(self, workspace_dir: str) -> bool:
        """执行 claude --version 判断 CLI 是否可用（线程池执行，兼容 Windows）。"""
        run_env = _subprocess_env(self.env)

        def _run_version() -> subprocess.CompletedProcess:
            return subprocess.run(
                ["claude", "--version"],
                env=run_env,
                capture_output=True,
                timeout=10,
            )

        try:
            loop = asyncio.get_event_loop()
            process = await loop.run_in_executor(_executor, _run_version)
            return process.returncode == 0
        except Exception:
            return False

    def _build_prompt(self, input: AgentInput) -> str:
        """将 AgentInput 转为发给 Claude CLI 的 prompt。

        结构：
        1. 当前会话成员 — 让 Agent 知道自己是谁、群里有哪些同事可协作
        2. 对话记录     — 历史消息（只读上下文）
        3. 当前待回复消息 — 从历史中提取的最后一条，Agent 只需回复这条
        4. 回复规则     — 简洁、SKIP、不重复历史
        5. 协作         — NEXT_MENTIONS 格式

        注意：role_prompt 不在这里注入——它已经写在 workspace_dir/CLAUDE.md 中，
        Claude CLI 会自动读取。
        """
        parts: list[str] = []

        # ── 1. 当前会话成员 ──
        agent_label = f"「{input.agent_name}」({input.agent_id})" if input.agent_name else f"({input.agent_id})"
        parts.append(f"## 当前会话成员\n你是{agent_label}。")
        if input.peers:
            parts.append("以下是本群的其他成员：")
            for p in input.peers:
                skills = ", ".join(p.skills) if p.skills else "无"
                parts.append(f"- {p.name} ({p.agent_id}) — 技能: {skills}")
        parts.append("")  # 空行分隔

        # ── 2. 对话记录（只读上下文）──
        if input.messages and len(input.messages) > 1:
            history = input.messages[:-1]
            parts.append("## 对话记录（只读上下文，不要回复这些历史消息）")
            for msg in history:
                author = msg.author_name or msg.role
                parts.append(f"[{author}]: {msg.content}")
            parts.append("")  # 空行分隔

        # ── 3. 记忆注入 ──
        if input.memory_context:
            parts.append(f"## 相关记忆\n{input.memory_context}\n")

        # ── 4. 当前待回复消息 ──
        parts.append("---\n")
        if input.messages:
            current = input.messages[-1]
            author = current.author_name or current.role
            parts.append("## 当前待回复消息")
            parts.append(f"发送者: {author}")
            parts.append(f"内容:\n{current.content}")
        parts.append("\n---\n")

        # ── 5. 回复规则 ──
        rules = ["## 回复规则"]
        rules.append("1. 只针对「当前待回复消息」回复，「对话记录」仅作为上下文参考，无需特别回复")
        if input.prefer_concise:
            rules.append("2. 简洁回复，突出关键信息")
        if input.invocation == "may_reply":
            rules.append("3. 如果你认为这条消息与你的职责无关，仅回复：SKIP")
        parts.append("\n".join(rules))

        # ── 6. 协作 ──
        parts.append(
            "\n## 协作\n"
            "如果你需要其他同事参与，在回复末尾用这个格式"
            "（agent_id 必须来自「当前会话成员」列表）：\n"
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
