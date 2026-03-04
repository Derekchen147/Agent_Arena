"""对话管理器：负责读写会话对话文件（conversations/{group_id}.md）。

每个会话（group）都有一个独立的对话记录文件，包含该会话中的所有消息。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.protocol import Message

logger = logging.getLogger(__name__)


class ConversationManager:
    """管理工作区的对话文件。"""

    def __init__(self, workspace_dir: str):
        """初始化对话管理器，指向工作区的 conversations 目录。"""
        self.workspace_dir = Path(workspace_dir)
        self.conversations_dir = self.workspace_dir / "conversations"
        self.conversations_dir.mkdir(parents=True, exist_ok=True)

    def get_conversation_path(self, group_id: str) -> Path:
        """获取特定会话的文件路径。"""
        # 使用 group_id 作为文件名，转义特殊字符
        safe_group_id = re.sub(r"[^\w-]", "_", group_id)
        return self.conversations_dir / f"{safe_group_id}.md"

    def append_message(self, group_id: str, message: Message) -> None:
        """将消息追加到会话文件末尾。"""
        path = self.get_conversation_path(group_id)

        # 格式化消息
        timestamp = message.timestamp.isoformat() if message.timestamp else datetime.now().isoformat()
        author = message.author_name or message.author_id or message.role

        line = f"[{timestamp}] **{author}**: {message.content}\n"

        # 追加到文件
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

        logger.debug(f"Appended message to {path}: {author}")

    def read_conversation(self, group_id: str) -> list[str]:
        """读取完整会话，返回行列表。"""
        path = self.get_conversation_path(group_id)

        if not path.exists():
            return []

        with open(path, "r", encoding="utf-8") as f:
            return f.readlines()

    def get_recent_messages(self, group_id: str, count: int = 5) -> str:
        """获取最近 N 条消息的文本。"""
        lines = self.read_conversation(group_id)

        if not lines:
            return ""

        # 取最后 count 行
        recent = lines[-count:]
        return "".join(recent).strip()

    def generate_summary(self, group_id: str, max_chars: int = 2000) -> str:
        """生成会话摘要（控制长度）。

        简单实现：取较早的消息（不包括最近5条），生成摘要。
        实际应该可以调用 LLM 生成更好的摘要，但这里先用简单方案。
        """
        lines = self.read_conversation(group_id)

        if len(lines) <= 5:
            # 消息太少，不需要摘要
            return ""

        # 取除最后5条以外的所有消息
        older_lines = lines[:-5]
        text = "".join(older_lines)

        # 如果已经很短，直接返回
        if len(text) <= max_chars:
            return f"### 早期对话背景\n{text}"

        # 截断到 max_chars
        truncated = text[:max_chars]
        # 找到最后一个完整行的结尾
        last_newline = truncated.rfind("\n")
        if last_newline > 0:
            truncated = truncated[:last_newline]

        return f"### 早期对话背景（已截断）\n{truncated}\n\n...[中间内容已省略]...\n"
