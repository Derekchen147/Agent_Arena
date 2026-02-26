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
import shutil
import subprocess
import tempfile
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

        # Windows 上 agent 安装为 .CMD 文件，即使 subprocess 用列表模式，
        # Python 也会通过 cmd.exe 执行 .cmd，而 cmd.exe 会在换行处截断参数。
        # 因此 Windows 始终用临时文件方案；非 Windows 优先列表模式。
        resolved: str | None = None
        if os.name != "nt":
            resolved = shutil.which(self.command, path=run_env.get("PATH"))

        # 写临时文件（Windows 始终需要；非 Windows 仅在找不到命令时使用）
        prompt_path: str | None = None
        if not resolved:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8",
            )
            tmp.write(prompt)
            tmp.close()
            prompt_path = tmp.name

        def _run_cmd() -> subprocess.CompletedProcess:
            if resolved:
                # 非 Windows 列表模式：prompt 作为独立参数，换行/引号等无截断风险
                cmd_list = [resolved, "-p", prompt, "--output-format", "json"] + self.extra_args
                logger.info("[CALL] cursor_cli: list-mode, resolved=%s", resolved)
                return subprocess.run(
                    cmd_list,
                    cwd=workspace_dir,
                    env=run_env,
                    capture_output=True,
                    timeout=self.timeout,
                )
            # 临时文件模式：从文件读取 prompt 避免截断
            base = f'"{self.command}"' if " " in self.command else self.command
            extra = " ".join(self.extra_args)
            if os.name == "nt":
                # Windows PowerShell: 用 Get-Content 读文件内容作为参数
                shell_cmd = (
                    f'powershell -NoProfile -Command "'
                    f"$p = Get-Content -Raw -Encoding UTF8 '{prompt_path}'; "
                    f'& {base} -p $p --output-format json {extra}"'
                )
            else:
                shell_cmd = f'{base} -p "$(cat \'{prompt_path}\')" --output-format json {extra}'.strip()
            logger.info("[CALL] cursor_cli: fallback shell cmd: %s", shell_cmd[:200])
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
        finally:
            if prompt_path:
                try:
                    os.unlink(prompt_path)
                except OSError:
                    pass

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

        结构：
        1. 当前会话成员 — 让 Agent 知道自己是谁、群里有哪些同事可协作
        2. 对话记录     — 历史消息（只读上下文）
        3. 当前待回复消息 — 从历史中提取的最后一条，Agent 只需回复这条
        4. 回复规则     — 简洁、SKIP、不重复历史
        5. 协作         — NEXT_MENTIONS 格式

        持久化角色/背景由 workspace_dir 下的 .cursor/rules/role.mdc 或 AGENTS.md 提供。
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

    def _parse_output(self, raw_output: str, input: AgentInput, prompt: str = "", duration_ms: int = 0) -> AgentOutput:
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

        meta = ExecutionMeta(duration_ms=duration_ms)
        logger.info("[CALL] cursor_cli parsed content =====> %s", content[:1000])
        return AgentOutput(
            content=content,
            next_mentions=next_mentions,
            should_respond=should_respond,
            execution_meta=meta,
            prompt_sent=prompt,
        )
