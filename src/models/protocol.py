"""Agent 与系统间的交互协议：Message、AgentInput、AgentOutput 等。

作为编排、上下文构建、Worker 调用的统一数据结构，不依赖具体存储格式。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """对话中的单条消息：角色、作者、内容、时间戳；用于构建 Agent 上下文。"""

    id: str = ""
    role: Literal["user", "assistant", "system"] = "user"
    author_id: str = ""
    author_name: str = ""
    content: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class StatusEvent(BaseModel):
    """Agent 运行时状态事件，可推送给前端做进度/动画展示。"""

    status: Literal[
        "idle", "analyzing", "reading_memory", "calling_tool",
        "generating", "reviewing", "waiting", "done", "error", "timeout",
    ] = "idle"
    detail: str = ""
    progress: float | None = None  # 0.0 ~ 1.0


class Attachment(BaseModel):
    """消息附件：类型、名称与数据（base64 或纯文本）。"""

    type: Literal["file", "code", "json", "image"] = "file"
    name: str = ""
    data: str = ""


class ToolCall(BaseModel):
    """单次工具调用记录：名称、输入参数与输出摘要。"""
    name: str = ""
    input: dict = Field(default_factory=dict)
    output: str = ""  # 截断后的输出摘要


class ExecutionMeta(BaseModel):
    """Agent 单次 CLI 调用的执行元数据（来自 stream-json 输出）。"""
    duration_ms: int = 0
    cost_usd: float = 0.0
    num_turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[ToolCall] = Field(default_factory=list)
    is_error: bool = False
    cli_session_id: str = ""


class Peer(BaseModel):
    """群组中的同事摘要，用于让 Agent 了解可协作的成员（不含自身）。"""

    agent_id: str
    name: str = ""
    skills: list[str] = Field(default_factory=list)


class AgentInput(BaseModel):
    """系统在一次调用中传给 Agent 的完整输入：会话、角色、历史、记忆与 token 限制。"""

    session_id: str
    turn_id: str
    agent_id: str
    agent_name: str = ""
    role_prompt: str = ""

    invocation: Literal["must_reply", "may_reply"] = "must_reply"
    mentioned_by: str | None = None

    messages: list[Message] = Field(default_factory=list)
    peers: list[Peer] = Field(default_factory=list)
    memory_context: str | None = None

    max_output_tokens: int = 2000
    prefer_concise: bool = True


class AgentOutput(BaseModel):
    """Agent 单次调用的返回：正文、下一轮 @ 名单、状态事件、附件及是否参与回复。"""

    content: str = ""
    next_mentions: list[str] = Field(default_factory=list)   # 链式召唤的 agent_id
    status_updates: list[StatusEvent] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    should_respond: bool = True   # may_reply 时由 Agent 自行决定是否回复
    execution_meta: ExecutionMeta | None = None
    prompt_sent: str = ""   # 完整 prompt，供 Orchestrator 写日志用，不广播给前端
