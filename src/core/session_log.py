"""按会话捕获 terminal 日志。

通过 contextvars 跟踪当前 group_id，自定义 logging.Handler
将所有 Python logging 输出同时写入 data/logs/session_{group_id}.log 文件。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from pathlib import Path

# 当前请求所属的 group_id（会话 ID）
current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)

_LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


class SessionLogHandler(logging.Handler):
    """将日志按 session_id 路由到独立的 .log 文件。

    只有当 current_session_id 被设置时才写入；未设置时静默跳过。
    内部缓存已打开的文件句柄，避免频繁开关文件。
    """

    def __init__(self, log_dir: str = "data/logs"):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.setFormatter(logging.Formatter(_LOG_FORMAT))
        self._files: dict[str, open] = {}  # session_id -> file handle

    def _get_file(self, session_id: str):
        if session_id not in self._files:
            path = self.log_dir / f"session_{session_id}.log"
            self._files[session_id] = open(path, "a", encoding="utf-8")
        return self._files[session_id]

    def emit(self, record: logging.LogRecord) -> None:
        session_id = current_session_id.get()
        if not session_id:
            return
        try:
            msg = self.format(record)
            f = self._get_file(session_id)
            f.write(msg + "\n")
            f.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        for f in self._files.values():
            try:
                f.close()
            except Exception:
                pass
        self._files.clear()
        super().close()


def get_session_log_path(session_id: str, log_dir: str = "data/logs") -> Path | None:
    """返回会话日志文件路径（如果存在）。"""
    path = Path(log_dir) / f"session_{session_id}.log"
    return path if path.exists() else None
