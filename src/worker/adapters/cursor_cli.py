"""Cursor CLI Adapter：通过 subprocess 调用 Cursor Headless CLI。

核心逻辑：
- 在 Agent 的 workspace_dir 中执行 agent -p "prompt" --output-format json
- workspace_dir 中的 .cursor/rules、项目文件等作为 Agent 上下文
- 安装：curl https://cursor.com/install -fsS | bash（或 Windows 见官方文档）
- 需配置 CURSOR_API_KEY 或已在 Cursor 中登录
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

# 在线程池中执行 subprocess.run，避免 Windows 上 asyncio 默认事件循环不支持子进程的问题
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cursor_cli")


def _subprocess_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    """合并当前进程环境与 extra_env，供子进程使用。"""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return env


def _build_shell_cmd(command: str, prompt: str, extra_args: list[str]) -> str:
    """构建供 shell=True 使用的命令字符串。
    Windows 下用列表形式 subprocess 会找不到 agent（不走 shell PATH），故统一走 shell。
    """
    safe_prompt = prompt.replace('"', '\\"')
    base = f'"{command}"' if " " in command else command
    parts = [base, "-p", f'"{safe_prompt}"', "--output-format", "json"]
    parts.extend(extra_args)
    return " ".join(parts)


class CursorCliAdapter(BaseAdapter):
    """通过 Cursor Headless CLI 调用的 Adapter。

    调用方式：command -p "prompt" --output-format json
    工作目录：Agent 的 workspace_dir（.cursor/rules 等会生效）
    若 uvicorn 进程的 PATH 里没有 agent，请在 cli_config 里写 command 为完整路径（如 where agent 得到的路径）。
    可选：cli_config.extra_args 可加 --force 等；cli_config.env 可传环境变量。
    """

    def __init__(
        self,
        command: str = "agent",
        timeout: int = 300,
        extra_args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.command = command or "agent"
        self.timeout = timeout
        self.extra_args = extra_args or []
        self.env = env or {}

    async def invoke(
        self,
        input: AgentInput,
        workspace_dir: str,
        stream_callback: Callable[[str], None] | None = None,
    ) -> AgentOutput:
        """在 workspace_dir 下执行 agent -p "prompt" --output-format json，解析为 AgentOutput。"""
        prompt = self._build_prompt(input)

        # 使用 shell 命令字符串，避免 Windows 下找不到 agent（不走 PATH）
        cmd_str = _build_shell_cmd(self.command, prompt, self.extra_args)
        logger.info(f"[CALL] cursor_cli.cmd: {cmd_str[:200]}…" if len(cmd_str) > 200 else f"[CALL] cursor_cli.cmd: {cmd_str}")

        logger.info(
            "[CALL] cursor_cli.invoke: agent_id=%s workspace_dir=%s prompt_len=%d extra_args=%s",
            input.agent_id,
            workspace_dir,
            len(prompt),
            self.extra_args,
        )
        logger.info(
            "[CALL] cursor_cli assembled prompt preview (first 300 chars): %s",
            (prompt[:300] + "…") if len(prompt) > 300 else prompt,
        )

        run_env = _subprocess_env(self.env)

        def _run_cmd() -> subprocess.CompletedProcess:
            return subprocess.run(
                cmd_str,
                cwd=workspace_dir,
                env=run_env,
                capture_output=True,
                timeout=self.timeout,
                shell=True,
            )

        try:
            loop = asyncio.get_event_loop()
            process = await loop.run_in_executor(_executor, _run_cmd)
            raw_output = (process.stdout or b"").decode("utf-8", errors="replace").strip()
            stderr_bytes = process.stderr or b""
            err = stderr_bytes.decode("utf-8", errors="replace").strip()

            if process.returncode != 0:
                logger.error(
                    "[CALL] Cursor CLI non-zero exit: agent_id=%s returncode=%s stderr=%s stdout_preview=%s",
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
                "[CALL] cursor_cli: agent_id=%s exit 0 output_len=%d",
                input.agent_id,
                len(raw_output),
            )
            return self._parse_output(raw_output, input)

        except subprocess.TimeoutExpired:
            logger.error(
                "[CALL] Cursor CLI timeout: agent_id=%s timeout=%ss",
                input.agent_id,
                self.timeout,
            )
            return AgentOutput(content="[Timeout] CLI 响应超时", should_respond=True)
        except FileNotFoundError:
            logger.error(
                "[CALL] Cursor CLI not found (not on PATH). agent_id=%s workspace_dir=%s",
                input.agent_id,
                workspace_dir,
            )
            return AgentOutput(
                content="[Error] agent 命令未找到，请先安装 Cursor CLI：https://cursor.com/docs/cli/installation",
                should_respond=True,
            )
        except Exception as e:
            logger.error(
                "[CALL] cursor_cli.invoke exception: agent_id=%s error=%s",
                input.agent_id,
                e,
                exc_info=True,
            )
            raise

    async def health_check(self, workspace_dir: str) -> bool:
        """执行 agent --version 或简短 -p 判断 CLI 是否可用（线程池执行，兼容 Windows）。"""
        run_env = _subprocess_env(self.env)
        base = f'"{self.command}"' if " " in self.command else self.command

        def _run_version() -> subprocess.CompletedProcess:
            return subprocess.run(
                f"{base} --version",
                env=run_env,
                capture_output=True,
                timeout=10,
                shell=True,
            )

        def _run_ok() -> subprocess.CompletedProcess:
            return subprocess.run(
                _build_shell_cmd(self.command, "ok", []),
                cwd=workspace_dir,
                env=run_env,
                capture_output=True,
                timeout=15,
                shell=True,
            )

        loop = asyncio.get_event_loop()
        try:
            process = await loop.run_in_executor(_executor, _run_version)
            if process.returncode == 0:
                return True
        except FileNotFoundError:
            return False
        except Exception:
            pass
        try:
            process = await loop.run_in_executor(_executor, _run_ok)
            return process.returncode == 0
        except Exception:
            return False

    def _build_prompt(self, input: AgentInput) -> str:
        """将 AgentInput 转为发给 Cursor CLI 的 prompt。

        角色/规则由 workspace_dir 下的 .cursor/rules 等提供，这里只拼对话与指引。
        """
        parts = []

        if input.role_prompt:
            parts.append(f"## 你的角色\n{input.role_prompt}\n")

        if input.messages:
            parts.append("## 当前对话")
            for msg in input.messages:
                author = msg.author_name or msg.role
                parts.append(f"[{author}]: {msg.content}")

        if input.memory_context:
            parts.append(f"\n## 相关记忆\n{input.memory_context}")

        if input.invocation == "may_reply":
            parts.append(
                "\n## 注意\n"
                "如果你认为这条消息与你的职责无关，请只回复：SKIP"
            )

        if input.prefer_concise:
            parts.append("\n请简洁回复，突出关键信息。")

        parts.append(
            "\n## 协作\n"
            "如果你需要其他同事参与，在回复末尾用这个格式：\n"
            "<!--NEXT_MENTIONS:[\"agent_id_1\",\"agent_id_2\"]-->"
        )

        return "\n".join(parts)

    def _parse_output(self, raw_output: str, input: AgentInput) -> AgentOutput:
        """从 CLI 输出解析：优先 JSON 的 result/content，再处理 SKIP 与 NEXT_MENTIONS。"""
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
