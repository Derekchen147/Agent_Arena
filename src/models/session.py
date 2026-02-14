"""会话相关数据模型：群组配置、成员、群组本身及持久化消息。

与 protocol 的区别：这里侧重存储与 API 展示，含 group_id、turn_id、metadata 等。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GroupConfig(BaseModel):
    """群组级编排与行为配置：每回合人数上限、超时、链深度、是否启用主管等。"""

    max_responders: int = 5
    turn_timeout_seconds: int = 120
    chain_depth_limit: int = 5
    re_invoke_already_replied: bool = False
    supervisor_enabled: bool = False
    supervisor_agent_id: str = "supervisor"
    auto_summary_interval: int = 20  # 每 N 条消息触发一次自动摘要


class GroupMember(BaseModel):
    """群组内一名成员：人类或 Agent；若为 Agent 则用 agent_id 关联注册表。"""

    id: str = ""
    type: Literal["human", "agent"] = "agent"
    agent_id: str | None = None
    display_name: str = ""
    joined_at: datetime = Field(default_factory=datetime.now)
    role_in_group: str | None = None  # 在本群中的角色描述，可覆盖默认角色


class Group(BaseModel):
    """群组：ID、名称、描述、创建时间、成员列表与群组配置。"""

    id: str = ""
    name: str = ""
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    members: list[GroupMember] = Field(default_factory=list)
    config: GroupConfig = Field(default_factory=GroupConfig)


class StoredMessage(BaseModel):
    """持久化到 DB 的消息结构：比 protocol.Message 多 group_id、turn_id、mentions、metadata。"""

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
