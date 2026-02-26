"""调用日志：按群聊会话记录每次 Agent 调用的完整信息。

每个会话的日志存在 data/logs/session_{session_id}.jsonl 文件中，
每行一条 JSON 记录（JSONL 格式），便于追加和逐行读取。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CallLog(BaseModel):
    """单次 Agent 调用的完整记录。"""
    log_id: str = ""
    session_id: str = ""
    turn_id: str = ""
    agent_id: str = ""
    agent_name: str = ""
    invocation: str = "must_reply"
    prompt_preview: str = ""     # 完整 prompt，不截断
    raw_output_preview: str = "" # 完整原始 CLI 输出（若 adapter 提供）
    content_preview: str = ""    # 完整解析后的响应，不截断
    duration_ms: int = 0
    cost_usd: float = 0.0
    num_turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[dict] = Field(default_factory=list)
    is_error: bool = False
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class CallLogger:
    """按会话写入/读取调用日志（JSONL 格式）。"""

    def __init__(self, log_dir: str = "data/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _session_file(self, session_id: str) -> Path:
        return self.log_dir / f"session_{session_id}.jsonl"

    def save(self, log: CallLog) -> None:
        """追加一条日志到该会话文件。"""
        path = self._session_file(log.session_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(log.model_dump_json() + "\n")
        logger.debug(
            "CallLogger: saved log for agent=%s turn=%s duration=%dms",
            log.agent_id, log.turn_id, log.duration_ms,
        )

    def get_session_logs(self, session_id: str) -> list[CallLog]:
        """读取该会话全部日志，按时间倒序返回。"""
        path = self._session_file(session_id)
        if not path.exists():
            return []
        logs: list[CallLog] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    logs.append(CallLog.model_validate_json(line))
                except Exception:
                    pass
        return list(reversed(logs))  # 最新的在最前
