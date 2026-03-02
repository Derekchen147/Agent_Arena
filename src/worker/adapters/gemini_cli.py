"""Gemini CLI Adapter：通过 subprocess 调用 Gemini Code CLI。

核心逻辑：
- 在 Agent 的 workspace_dir 中启动 gemini 命令
- 使用 gemini -p "prompt" --output-format json --approval-mode yolo
- 为避免 Windows shell 截断多行 prompt，使用临时文件读取方式
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

# 在线程池中执行 subprocess.run，避免 Windows 上 asyncio 默认事件循环不支持子进程的问题
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gemini_cli")


def _subprocess_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    """合并当前进程环境与 extra_env，供子进程使用。

    代理配置应通过 Agent 的 cli_config.env 传入（如 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY），
    不在此处硬编码默认值，以兼容无需代理的环境。
    """
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return env


class GeminiCliAdapter(BaseAdapter):
    """通过 Gemini Code CLI 调用的 Adapter。

    调用方式：gemini -p "prompt" --output-format json --approval-mode yolo
    工作目录：Agent 的 workspace_dir
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
        """在 workspace_dir 下执行 gemini，解析为 AgentOutput。"""
        prompt = self._build_prompt(input)

        logger.info(
            "[CALL] gemini_cli.invoke: agent_id=%s workspace_dir=%s prompt_len=%d extra_args=%s",
            input.agent_id,
            workspace_dir,
            len(prompt),
            self.extra_args,
        )
        logger.info("[CALL] gemini_cli assembled prompt =====> %s", prompt)

        run_env = _subprocess_env(self.env)
        start_time = time.monotonic()

        # 使用临时文件方案避免命令行截断（特别是 Windows）
        prompt_path: str | None = None
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8",
        )
        tmp.write(prompt)
        tmp.close()
        prompt_path = tmp.name

        def _run_cmd() -> subprocess.CompletedProcess:
            extra = " ".join(self.extra_args)
            if os.name == "nt":
                # Windows PowerShell: 用 Get-Content 读文件内容作为参数
                shell_cmd = (
                    f'powershell -NoProfile -Command "'
                    f"$p = Get-Content -Raw -Encoding UTF8 '{prompt_path}'; "
                    f'gemini -p `"$p`" --output-format json --approval-mode yolo {extra}"'
                )
            else:
                # 非 Windows
                shell_cmd = f'gemini -p "$(cat "{prompt_path}")" --output-format json --approval-mode yolo {extra}'.strip()
            
            logger.info("[CALL] gemini_cli shell cmd: %s", shell_cmd[:200])
            return subprocess.run(
                shell_cmd,
                cwd=workspace_dir,
                env=run_env,
                capture_output=True,
                timeout=self.timeout,
                shell=True,
            )

        try:
            loop = asyncio.get_event_loop()
            process = await loop.run_in_executor(_executor, _run_cmd)
            duration_ms = int((time.monotonic() - start_time) * 1000)
        except subprocess.TimeoutExpired:
            logger.error(
                "[CALL] Gemini CLI timeout: agent_id=%s timeout=%ss",
                input.agent_id,
                self.timeout,
            )
            return AgentOutput(content="[Timeout] CLI 响应超时", should_respond=True)
        except Exception as e:
            logger.error(
                "[CALL] gemini_cli.invoke exception: agent_id=%s error=%s",
                input.agent_id,
                e,
                exc_info=True,
            )
            raise
        finally:
            if prompt_path:
                try:
                    os.unlink(prompt_path)
                except OSError:
                    pass

        raw_output = (process.stdout or b"").decode("utf-8", errors="replace").strip()
        err = (process.stderr or b"").decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            logger.error(
                "[CALL] Gemini CLI non-zero exit: agent_id=%s returncode=%s stderr=%s stdout_preview=%s",
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
            "[CALL] gemini_cli: agent_id=%s exit 0 output_len=%d duration_ms=%d",
            input.agent_id,
            len(raw_output),
            duration_ms,
        )
        logger.info("[CALL] gemini_cli raw_output =====> %s", raw_output[:3000])
        return self._parse_output(raw_output, input, prompt, duration_ms)

    async def health_check(self, workspace_dir: str) -> bool:
        """检查 gemini --version 是否可用。"""
        run_env = _subprocess_env(self.env)

        def _run_version() -> subprocess.CompletedProcess:
            return subprocess.run(
                "gemini --version",
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
        """构建 Prompt，逻辑同 ClaudeCliAdapter。"""
        parts: list[str] = []

        # 1. 当前会话成员
        agent_label = f"「{input.agent_name}」({input.agent_id})" if input.agent_name else f"({input.agent_id})"
        parts.append(f"## 当前会话成员\n你是{agent_label}。")
        if input.peers:
            parts.append("以下是本群的其他成员：")
            for p in input.peers:
                skills = ", ".join(p.skills) if p.skills else "无"
                parts.append(f"- {p.name} ({p.agent_id}) — 技能: {skills}")
        parts.append("")

        # 2. 对话记录
        if input.messages and len(input.messages) > 1:
            history = input.messages[:-1]
            parts.append("## 对话记录（只读上下文，不要回复这些历史消息）")
            for msg in history:
                author = msg.author_name or msg.role
                parts.append(f"[{author}]: {msg.content}")
            parts.append("")

        # 3. 记忆注入
        if input.memory_context:
            parts.append(f"## 相关记忆\n{input.memory_context}\n")

        # 4. 当前待回复消息
        parts.append("---\n")
        if input.messages:
            current = input.messages[-1]
            author = current.author_name or current.role
            parts.append("## 当前待回复消息")
            parts.append(f"发送者: {author}")
            parts.append(f"内容:\n{current.content}")
        parts.append("\n---\n")

        # 5. 回复规则
        rules = ["## 回复规则"]
        rules.append("1. 只针对「当前待回复消息」回复，「对话记录」仅作为上下文参考，无需特别回复")
        if input.prefer_concise:
            rules.append("2. 简洁回复，突出关键信息")
        if input.invocation == "may_reply":
            rules.append("3. 如果你认为这条消息与你的职责无关，仅回复：SKIP")
        parts.append("\n".join(rules))

        # 6. 协作
        parts.append(
            "\n## 协作\n"
            "如果你需要其他同事参与，在回复末尾用这个格式"
            "（agent_id 必须来自「当前会话成员」列表）：\n"
            "<!--NEXT_MENTIONS:[\"agent_id_1\",\"agent_id_2\"]-->"
        )

        return "\n".join(parts)

    def _parse_output(self, raw_output: str, input: AgentInput, prompt: str = "", duration_ms: int = 0) -> AgentOutput:
        """从 CLI 输出解析。"""
        content = raw_output

        # 尝试解析 JSON
        try:
            data = json.loads(raw_output)
            if isinstance(data, dict):
                # 兼容不同的输出字段
                content = data.get("result", data.get("content", raw_output))
            elif isinstance(data, list):
                text_parts = [
                    block.get("text", "")
                    for block in data
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                content = "\n".join(text_parts) if text_parts else raw_output
        except json.JSONDecodeError:
            # 如果不是 JSON，可能是 NDJSON 或纯文本
            # 处理 NDJSON (类似 Claude CLI)
            final_result_text = None
            for line in raw_output.strip().split('\n'):
                line = line.strip()
                if not line: continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "result":
                        final_result_text = event.get("result")
                except json.JSONDecodeError:
                    continue
            if final_result_text:
                content = final_result_text

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

        meta = ExecutionMeta(duration_ms=duration_ms)
        return AgentOutput(
            content=content,
            next_mentions=next_mentions,
            should_respond=should_respond,
            execution_meta=meta,
            prompt_sent=prompt,
        )
