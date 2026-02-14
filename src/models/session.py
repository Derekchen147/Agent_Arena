"""会话相关数据模型：Group / GroupMember / StoredMessage。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GroupConfig(BaseModel):
    """群组级配置。"""

    max_responders: int = 5
    turn_timeout_seconds: int = 120
    chain_depth_limit: int = 5
    re_invoke_already_replied: bool = False
    supervisor_enabled: bool = False
    supervisor_agent_id: str = "supervisor"
    auto_summary_interval: int = 20  # 每 N 条消息自动生成摘要


class GroupMember(BaseModel):
    """群组成员。"""

    id: str = ""
    type: Literal["human", "agent"] = "agent"
    agent_id: str | None = None  # 如果是 AI 员工，关联到 AgentRegistry
    display_name: str = ""
    joined_at: datetime = Field(default_factory=datetime.now)
    role_in_group: str | None = None  # 在本群组中的角色（可覆盖默认角色）


class Group(BaseModel):
    """群组。"""

    id: str = ""
    name: str = ""
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    members: list[GroupMember] = Field(default_factory=list)
    config: GroupConfig = Field(default_factory=GroupConfig)


class StoredMessage(BaseModel):
    """持久化存储的消息（比 protocol.Message 多了群组/回合等元数据）。"""

    id: str = ""
    group_id: str = ""
    turn_id: str = ""
    author_id: str = ""
    author_type: Literal["human", "agent", "system"] = "human"
    author_name: str = ""
    content: str = ""
    mentions: list[str] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)
