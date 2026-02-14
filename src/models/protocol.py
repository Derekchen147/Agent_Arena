"""Agent 交互协议：AgentInput / AgentOutput，全系统的基石。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """会话中的一条消息。"""

    id: str = ""
    role: Literal["user", "assistant", "system"] = "user"
    author_id: str = ""
    author_name: str = ""
    content: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class StatusEvent(BaseModel):
    """Agent 状态事件，用于驱动前端动画。"""

    status: Literal[
        "idle",
        "analyzing",
        "reading_memory",
        "calling_tool",
        "generating",
        "reviewing",
        "waiting",
        "done",
        "error",
        "timeout",
    ] = "idle"
    detail: str = ""
    progress: float | None = None  # 0.0 ~ 1.0


class Attachment(BaseModel):
    """消息附件。"""

    type: Literal["file", "code", "json", "image"] = "file"
    name: str = ""
    data: str = ""  # base64 或文本内容


class AgentInput(BaseModel):
    """系统发给 Agent 的输入。"""

    # 身份与会话
    session_id: str
    turn_id: str
    agent_id: str
    role_prompt: str = ""

    # 响应要求
    invocation: Literal["must_reply", "may_reply"] = "must_reply"
    mentioned_by: str | None = None

    # 消息上下文（已经过截断/摘要处理）
    messages: list[Message] = Field(default_factory=list)

    # 记忆注入
    memory_context: str | None = None

    # Token 控制
    max_output_tokens: int = 2000
    prefer_concise: bool = True


class AgentOutput(BaseModel):
    """Agent 返回给系统的输出。"""

    # 必填
    content: str = ""

    # 链式调用：希望下一轮强制回复的 agent_id 列表
    next_mentions: list[str] = Field(default_factory=list)

    # 状态上报
    status_updates: list[StatusEvent] = Field(default_factory=list)

    # 附件
    attachments: list[Attachment] = Field(default_factory=list)

    # 自我判断（仅 may_reply 时有效）
    should_respond: bool = True
