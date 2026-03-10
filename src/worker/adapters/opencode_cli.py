"""OpenCode CLI Adapter：通过 subprocess 调用 opencode CLI。

核心逻辑：
- 在 Agent 的 workspace_dir 中启动 opencode 命令
- 使用 opencode run --format json "prompt" 调用
- Windows 下用临时文件 + PowerShell Get-Content 传递 prompt，避免换行截断
- 解析 NDJSON 输出：type=text 拼接文本，type=step_finish 提取 tokens/cost
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from src.models.protocol import AgentInput, AgentOutput, ExecutionMeta
from src.worker.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="opencode_cli")


def _subprocess_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    """合并当前进程环境与 extra_env，供子进程使用。"""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return env


class OpencodeCliAdapter(BaseAdapter):
    """通过 opencode CLI 调用的 Adapter。

    调用方式：opencode run --format json [-m model] "prompt"
    工作目录：Agent 的 workspace_dir（subprocess cwd）
    Windows 换行处理：写临时文件，PowerShell Get-Content -Raw 读取，避免 shell 截断。

    agent.yaml 示例：
        cli_config:
          cli_type: opencode
          command: anthropic/claude-sonnet-4-5   # 模型，留空则用 opencode 默认
          timeout: 300
    """

    def __init__(
        self,
        model: str | None = None,
        timeout: int = 60 * 40,
        extra_args: list[str] | None = None,
        env: dict[str, str] | None = None,
        mcp_config=None,
        skill_definitions=None,
    ):
        self.model = model or ""
        self.timeout = timeout
        self.extra_args = extra_args or []
        self.env = env or {}
        self.mcp_config = mcp_config
        self.skill_definitions = skill_definitions or []

    async def invoke(
        self,
        input: AgentInput,
        workspace_dir: str,
        stream_callback: Callable[[str], None] | None = None,
    ) -> AgentOutput:
        """在 workspace_dir 下执行 opencode run，解析 NDJSON 为 AgentOutput。"""
        prompt = self._build_prompt(input)
        logger.info(
            "[CALL] opencode_cli.invoke: agent_id=%s workspace_dir=%s prompt_len=%d model=%s",
            input.agent_id,
            workspace_dir,
            len(prompt),
            self.model or "(default)",
        )
        logger.info("[CALL] opencode_cli assembled prompt =====> %s", prompt)

        run_env = _subprocess_env(self.env)
        start_time = time.monotonic()

        def _run_cmd() -> subprocess.CompletedProcess:
            prompt_path = None
            try:
                # 写临时文件，避免 Windows 命令行换行符问题
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                )
                tmp.write(prompt)
                tmp.close()
                prompt_path = tmp.name

                model_args = f"-m {self.model} " if self.model else ""
                extra = " ".join(self.extra_args) + " " if self.extra_args else ""

                if os.name == "nt":
                    # PowerShell 读文件内容后作为变量传入，保留换行
                    shell_cmd = (
                        f'powershell -NoProfile -Command "'
                        f"$p = Get-Content -Raw -Encoding UTF8 '{prompt_path}'; "
                        f'opencode run --format json {model_args}{extra}$p"'
                    )
                else:
                    shell_cmd = (
                        f'opencode run --format json {model_args}{extra}'
                        f'"$(cat \'{prompt_path}\')"'
                    )

                logger.info("[CALL] opencode_cli shell_cmd: %s", shell_cmd[:200])
                return subprocess.run(
                    shell_cmd,
                    cwd=workspace_dir,
                    env=run_env,
                    capture_output=True,
                    timeout=self.timeout,
                    shell=True,
                )
            finally:
                if prompt_path:
                    try:
                        os.unlink(prompt_path)
                    except OSError:
                        pass

        try:
            loop = asyncio.get_event_loop()
            process = await loop.run_in_executor(_executor, _run_cmd)
            duration_ms = int((time.monotonic() - start_time) * 1000)
        except subprocess.TimeoutExpired:
            logger.error(
                "[CALL] OpenCode CLI timeout: agent_id=%s timeout=%ss",
                input.agent_id,
                self.timeout,
            )
            return AgentOutput(content="[Timeout] CLI 响应超时", should_respond=True)
        except Exception as e:
            logger.error(
                "[CALL] opencode_cli.invoke exception: agent_id=%s error=%s",
                input.agent_id,
                e,
                exc_info=True,
            )
            raise

        raw_output = (process.stdout or b"").decode("utf-8", errors="replace").strip()
        err = (process.stderr or b"").decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            logger.error(
                "[CALL] OpenCode CLI non-zero exit: agent_id=%s returncode=%s stderr=%s stdout_preview=%s",
                input.agent_id,
                process.returncode,
                err,
                raw_output[:300] if raw_output else "",
            )
            return AgentOutput(
                content=f"[CLI Error] {err or raw_output}",
                should_respond=True,
                execution_meta=ExecutionMeta(duration_ms=duration_ms, is_error=True),
                prompt_sent=prompt,
            )

        logger.info(
            "[CALL] opencode_cli: agent_id=%s exit 0 output_len=%d duration_ms=%d",
            input.agent_id,
            len(raw_output),
            duration_ms,
        )
        logger.info("[CALL] opencode_cli raw_output =====> %s", raw_output[:3000])
        result = self._parse_output(raw_output, input, prompt, duration_ms)
        logger.info("[CALL] opencode_cli parsed content =====> %s", result.content[:1000])
        return result

    async def health_check(self, workspace_dir: str) -> bool:
        """执行 opencode --version 判断 CLI 是否可用。"""
        run_env = _subprocess_env(self.env)

        def _run_version() -> subprocess.CompletedProcess:
            return subprocess.run(
                "opencode --version",
                env=run_env,
                capture_output=True,
                timeout=10,
                shell=True,
            )

        try:
            loop = asyncio.get_event_loop()
            process = await loop.run_in_executor(_executor, _run_version)
            return process.returncode == 0
        except Exception:
            return False

    def _build_prompt(self, input: AgentInput) -> str:
        """将 AgentInput 转为发给 opencode CLI 的 prompt。"""
        return self._build_context_prompt(input)

    def _parse_output(
        self,
        raw_output: str,
        input: AgentInput,
        prompt: str = "",
        duration_ms: int = 0,
    ) -> AgentOutput:
        """解析 opencode --format json 的 NDJSON 输出。

        事件格式：
          {"type":"text",      "part":{"text":"...", ...}, "sessionID":"..."}
          {"type":"step_finish","part":{"reason":"stop","cost":0,"tokens":{...}}, "sessionID":"..."}
        """
        text_parts: list[str] = []
        meta = ExecutionMeta(duration_ms=duration_ms)

        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")
            part = event.get("part", {})

            if event_type == "text":
                text = part.get("text", "")
                if text:
                    text_parts.append(text)

            elif event_type == "step_finish":
                tokens = part.get("tokens", {})
                meta.input_tokens = tokens.get("input", 0)
                meta.output_tokens = tokens.get("output", 0)
                meta.cost_usd = part.get("cost", 0.0)
                meta.cli_session_id = event.get("sessionID", "")
                # reason: "stop" | "tool" | "error" | "length"
                if part.get("reason") == "error":
                    meta.is_error = True

        content = "".join(text_parts)

        # 兜底：无任何 text 事件时，尝试把整个输出当纯文本
        if not content:
            content = raw_output

        # SKIP 机制
        should_respond = True
        if content.strip() == "SKIP" or content.strip().startswith("SKIP"):
            should_respond = False
            content = ""

        # NEXT_MENTIONS
        next_mentions: list[str] = []
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
            execution_meta=meta,
            prompt_sent=prompt,
            raw_output=raw_output,
        )
