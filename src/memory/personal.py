"""Agent 个人记忆管理：读写 workspace 下的 MEMORY.md 和 memory/{date}.md。

每个 Agent 在其 workspace_dir 下拥有：
  - MEMORY.md              精华长期记忆，跨会话积累
  - memory/YYYY-MM-DD.md   每日原始工作日志
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# 注入上下文时的字符数上限（控制 Token 消耗）
_MEMORY_MD_MAX_CHARS = 2400   # ~600 tokens
_DAILY_LOG_MAX_CHARS = 1600   # ~400 tokens / 文件


class PersonalMemoryManager:
    """管理单个 Agent workspace 下的个人记忆文件。

    读取时合并 MEMORY.md + 近两日日志，作为 memory_context 的一部分注入。
    写入时追加到今日日志（由 Orchestrator 在解析 <!--PERSONAL_LOG:--> 标记时调用）。
    """

    def read_context(self, workspace_dir: str) -> str:
        """读取 MEMORY.md + 今日/昨日日志，返回结构化字符串；无内容返回空字符串。"""
        ws = Path(workspace_dir)
        parts: list[str] = []

        # ── 精华长期记忆 ──
        memory_md = ws / "MEMORY.md"
        if memory_md.exists():
            text = memory_md.read_text(encoding="utf-8").strip()
            if text:
                if len(text) > _MEMORY_MD_MAX_CHARS:
                    text = text[:_MEMORY_MD_MAX_CHARS] + "\n...(截断)"
                parts.append(f"### 个人长期记忆\n{text}")

        # ── 今日 / 昨日日志 ──
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        for date_str in [today, yesterday]:
            log_file = ws / "memory" / f"{date_str}.md"
            if log_file.exists():
                text = log_file.read_text(encoding="utf-8").strip()
                if text:
                    if len(text) > _DAILY_LOG_MAX_CHARS:
                        text = text[:_DAILY_LOG_MAX_CHARS] + "\n...(截断)"
                    parts.append(f"### {date_str} 工作日志\n{text}")

        return "\n\n".join(parts)

    def append_daily_log(self, workspace_dir: str, content: str) -> None:
        """向今日日志追加一条带时间戳的记录。"""
        ws = Path(workspace_dir)
        memory_dir = ws / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = memory_dir / f"{today}.md"
        timestamp = datetime.now().strftime("%H:%M")
        entry = f"\n- [{timestamp}] {content.strip()}\n"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.debug("PersonalMemory: appended to %s", log_file)

    def init_workspace_memory(self, workspace_dir: str, agent_name: str) -> None:
        """Onboard 时初始化：创建 memory/ 目录，若 MEMORY.md 不存在则写入模板。"""
        ws = Path(workspace_dir)
        (ws / "memory").mkdir(parents=True, exist_ok=True)

        memory_md = ws / "MEMORY.md"
        if not memory_md.exists():
            template = (
                f"# {agent_name} - 个人长期记忆\n\n"
                "> 记录跨会话的重要经验、决策模式和工作洞察。\n"
                "> 由 Orchestrator 在解析 <!--PERSONAL_LOG:--> 标记后写入，"
                "也可在心跳蒸馏时由 Agent 自主更新。\n\n"
            )
            memory_md.write_text(template, encoding="utf-8")
            logger.info("PersonalMemory: initialized MEMORY.md for %s", agent_name)
