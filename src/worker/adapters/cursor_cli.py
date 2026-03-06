"""Cursor CLI Adapter：通过 subprocess 调用 Cursor Headless CLI。

核心逻辑：
- 在 Agent 的 workspace_dir 中执行 agent -p "prompt" --output-format json
- System prompt / 角色与背景：由工作目录下的约定文件提供，Cursor 会自动加载：
  - .cursor/rules/*.mdc（推荐）：规则文件，可用 alwaysApply: true 使角色在每次对话生效
  - AGENTS.md：项目根下的纯 Markdown，作为简单替代
  接入 Cursor 类 Agent 时，WorkspaceManager 会写入 .cursor/rules/role.mdc，便于角色扮演与背景信息。
- 此外，本 adapter 在每次请求的 prompt 中也会附带 role_prompt（## 你的角色），作为补充。
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
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from src.models.protocol import AgentInput, AgentOutput, ExecutionMeta
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
        timeout: int = 60 * 40,
        extra_args: list[str] | None = None,
        env: dict[str, str] | None = None,
        mcp_config=None,
        skill_definitions=None,
    ):
        self.command = command or "agent"
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
        """在 workspace_dir 下执行 agent -p "prompt" --output-format json，解析为 AgentOutput。

        为避免 Windows shell 截断多行 prompt（换行符被当作命令分隔符），
        优先用 shutil.which 解析命令路径后以列表参数调用（不走 shell），
        回退时将 prompt 写入临时文件再通过 shell 读取。
        """
        prompt = self._build_prompt(input)

        logger.info(
            "[CALL] cursor_cli.invoke: agent_id=%s workspace_dir=%s prompt_len=%d extra_args=%s",
            input.agent_id,
            workspace_dir,
            len(prompt),
            self.extra_args,
        )
        logger.info("[CALL] cursor_cli assembled prompt =====> / %s",prompt)

        run_env = _subprocess_env(self.env)
        start_time = time.monotonic()
        prompt_bytes = prompt.encode("utf-8")

        # 生成 MCP 配置文件（如果有）
        mcp_config_path = None
        if self.mcp_config:
            from src.mcp.loader import generate_claude_mcp_json
            mcp_config_path = generate_claude_mcp_json(
                self.mcp_config, workspace_dir, extra_env=self.env,
            )

        def _run_cmd() -> subprocess.CompletedProcess:
            # 通过 stdin 管道传递 prompt，避免 shell 转义和命令行长度限制
            # 非交互调用必须信任工作目录，否则会报 Workspace Trust Required
            cmd = [
                self.command,
                "--output-format", "json",
                "--trust",
                "--yolo",
                *self.extra_args,
            ]
            logger.info("[CALL] cursor_cli cmd: %s (stdin prompt_len=%d)", cmd, len(prompt_bytes))
            return subprocess.run(
                cmd,
                input=prompt_bytes,
                cwd=workspace_dir,
                env=run_env,
                capture_output=True,
                timeout=self.timeout,
                shell=(os.name == "nt"),  # Windows 上 .cmd 文件需要 shell
            )

        try:
            loop = asyncio.get_event_loop()
            process = await loop.run_in_executor(_executor, _run_cmd)
            duration_ms = int((time.monotonic() - start_time) * 1000)
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
                execution_meta=ExecutionMeta(duration_ms=duration_ms, is_error=True),
                prompt_sent=prompt,
            )

        logger.info(
            "[CALL] cursor_cli: agent_id=%s exit 0 output_len=%d duration_ms=%d",
            input.agent_id,
            len(raw_output),
            duration_ms,
        )
        logger.info("[CALL] cursor_cli raw_output =====> %s", raw_output[:3000])
        return self._parse_output(raw_output, input, prompt, duration_ms)

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
                [self.command, "--output-format", "json", "--trust", "--yolo"],
                input=b"ok",
                env=run_env,
                capture_output=True,
                timeout=15,
                shell=(os.name == "nt"),
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

        使用基类的 _build_context_prompt 方法构造动态上下文部分。
        """
        return self._build_context_prompt(input)

    def _parse_output(self, raw_output: str, input: AgentInput, prompt: str = "", duration_ms: int = 0) -> AgentOutput:
        """从 CLI 输出解析：优先 JSON 的 result/content，再处理 SKIP 与 NEXT_MENTIONS；从 usage 提取 token 统计。"""
        content = raw_output
        usage_data: dict = {}

        try:
            data = json.loads(raw_output)
            if isinstance(data, dict):
                content = data.get("result", data.get("content", raw_output))
                usage_data = data.get("usage") or {}
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

        # Cursor CLI 返回 usage: { inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens }（camelCase）
        input_tokens = (
            usage_data.get("inputTokens", 0)
            + usage_data.get("cacheReadTokens", 0)
        )
        output_tokens = usage_data.get("outputTokens", 0)
        meta = ExecutionMeta(
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        if usage_data and (input_tokens or output_tokens):
            logger.info(
                "[CALL] cursor_cli usage: input_tokens=%d output_tokens=%d",
                input_tokens,
                output_tokens,
            )
        logger.info("[CALL] cursor_cli parsed content =====> %s", content[:1000])
        return AgentOutput(
            content=content,
            next_mentions=next_mentions,
            should_respond=should_respond,
            execution_meta=meta,
            prompt_sent=prompt,
            raw_output=raw_output,
        )
