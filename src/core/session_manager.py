"""会话管理器：管理群组、消息、成员的 CRUD 和持久化存储。

纯数据层，不包含编排或业务逻辑；所有表结构由 DB_SCHEMA 定义，使用 aiosqlite 异步读写。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import aiosqlite

from src.models.protocol import Attachment, Message
from src.models.session import Group, GroupConfig, GroupMember, StoredMessage

# 数据库表结构：群组、群成员、消息；含索引以加速按 group_id / timestamp 查询
DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    config TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS group_members (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'agent',
    agent_id TEXT,
    display_name TEXT DEFAULT '',
    joined_at TEXT NOT NULL,
    role_in_group TEXT,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    turn_id TEXT DEFAULT '',
    author_id TEXT NOT NULL,
    author_type TEXT NOT NULL DEFAULT 'human',
    author_name TEXT DEFAULT '',
    content TEXT DEFAULT '',
    mentions TEXT DEFAULT '[]',
    attachments TEXT DEFAULT '[]',
    timestamp TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_group_id ON messages(group_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_group_members_group_id ON group_members(group_id);
"""


class SessionManager:
    """会话管理器：提供群组、成员、消息的增删改查与持久化，不包含业务编排。"""

    def __init__(self, db_path: str = "data/agent_arena.db"):
        """指定 SQLite 数据库文件路径，连接在 initialize() 中建立。"""
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """连接数据库、设置 Row 工厂、执行建表脚本并提交。应用启动时调用一次。"""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(DB_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        """关闭数据库连接。应用关闭时调用。"""
        if self._db:
            await self._db.close()

    # ── 群组 CRUD ──

    async def create_group(self, name: str, description: str = "", config: GroupConfig | None = None) -> Group:
        """创建新群组：生成 UUID、写入 groups 表并返回 Group 模型。"""
        group_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        cfg = config or GroupConfig()
        await self._db.execute(
            "INSERT INTO groups (id, name, description, created_at, config) VALUES (?, ?, ?, ?, ?)",
            (group_id, name, description, now, cfg.model_dump_json()),
        )
        await self._db.commit()
        return Group(id=group_id, name=name, description=description, created_at=now, config=cfg)

    async def get_group(self, group_id: str) -> Group | None:
        """根据 group_id 查询群组；若存在则附带成员列表并解析 config JSON。"""
        cursor = await self._db.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        members = await self.list_group_members(group_id)
        return Group(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            members=members,
            config=GroupConfig.model_validate_json(row["config"]),
        )

    async def list_groups(self) -> list[Group]:
        """列出所有群组，按创建时间倒序；每条记录均附带成员列表。"""
        cursor = await self._db.execute("SELECT * FROM groups ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        groups = []
        for row in rows:
            members = await self.list_group_members(row["id"])
            groups.append(Group(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                created_at=row["created_at"],
                members=members,
                config=GroupConfig.model_validate_json(row["config"]),
            ))
        return groups

    async def delete_group(self, group_id: str) -> None:
        """删除指定群组；外键 CASCADE 会一并删除该群的消息与成员记录。"""
        await self._db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        await self._db.commit()

    # ── 成员管理 ──

    async def add_member(
        self,
        group_id: str,
        member_type: str = "agent",
        agent_id: str | None = None,
        display_name: str = "",
        role_in_group: str | None = None,
    ) -> GroupMember:
        """向指定群组添加一名成员（人类或 Agent），写入 group_members 表并返回模型。"""
        member_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        await self._db.execute(
            "INSERT INTO group_members (id, group_id, type, agent_id, display_name, joined_at, role_in_group) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (member_id, group_id, member_type, agent_id, display_name, now, role_in_group),
        )
        await self._db.commit()
        return GroupMember(
            id=member_id, type=member_type, agent_id=agent_id,
            display_name=display_name, joined_at=now, role_in_group=role_in_group,
        )

    async def remove_member(self, group_id: str, member_id: str) -> None:
        """从群组中移除指定成员；仅删除 group_members 记录，不删消息。"""
        await self._db.execute(
            "DELETE FROM group_members WHERE id = ? AND group_id = ?",
            (member_id, group_id),
        )
        await self._db.commit()

    async def list_group_members(self, group_id: str) -> list[GroupMember]:
        """按加入时间正序列出该群组所有成员。"""
        cursor = await self._db.execute(
            "SELECT * FROM group_members WHERE group_id = ? ORDER BY joined_at", (group_id,)
        )
        rows = await cursor.fetchall()
        return [
            GroupMember(
                id=row["id"],
                type=row["type"],
                agent_id=row["agent_id"],
                display_name=row["display_name"],
                joined_at=row["joined_at"],
                role_in_group=row["role_in_group"],
            )
            for row in rows
        ]

    # ── 消息存储 ──

    async def save_message(
        self,
        group_id: str,
        author_id: str,
        content: str,
        author_type: str = "human",
        author_name: str = "",
        turn_id: str = "",
        mentions: list[str] | None = None,
        attachments: list[Attachment] | None = None,
        metadata: dict | None = None,
    ) -> StoredMessage:
        """将一条消息写入 messages 表；支持 @mentions、附件与 metadata，返回 StoredMessage。"""
        msg_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        msg = StoredMessage(
            id=msg_id,
            group_id=group_id,
            turn_id=turn_id,
            author_id=author_id,
            author_type=author_type,
            author_name=author_name,
            content=content,
            mentions=mentions or [],
            attachments=[a.model_dump() for a in attachments] if attachments else [],
            timestamp=now,
            metadata=metadata or {},
        )
        await self._db.execute(
            "INSERT INTO messages (id, group_id, turn_id, author_id, author_type, author_name, "
            "content, mentions, attachments, timestamp, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                msg.id, msg.group_id, msg.turn_id, msg.author_id,
                msg.author_type, msg.author_name, msg.content,
                json.dumps(msg.mentions), json.dumps(msg.attachments),
                msg.timestamp, json.dumps(msg.metadata),
            ),
        )
        await self._db.commit()
        return msg

    async def get_messages(
        self, group_id: str, limit: int = 50, before: str | None = None
    ) -> list[StoredMessage]:
        """分页获取群组消息：支持 before 游标；结果按时间正序（从旧到新）。"""
        if before:
            cursor = await self._db.execute(
                "SELECT * FROM messages WHERE group_id = ? AND timestamp < ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (group_id, before, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM messages WHERE group_id = ? ORDER BY timestamp DESC LIMIT ?",
                (group_id, limit),
            )
        rows = await cursor.fetchall()
        messages = [
            StoredMessage(
                id=row["id"],
                group_id=row["group_id"],
                turn_id=row["turn_id"],
                author_id=row["author_id"],
                author_type=row["author_type"],
                author_name=row["author_name"],
                content=row["content"],
                mentions=json.loads(row["mentions"]),
                attachments=json.loads(row["attachments"]),
                timestamp=row["timestamp"],
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]
        messages.reverse()  # 按时间正序返回，便于前端展示
        return messages

    def stored_to_protocol(self, stored: StoredMessage) -> Message:
        """将 StoredMessage 转为 protocol.Message（供 ContextBuilder 等构建对话上下文使用）。"""
        role = "user" if stored.author_type == "human" else (
            "system" if stored.author_type == "system" else "assistant"
        )
        return Message(
            id=stored.id,
            role=role,
            author_id=stored.author_id,
            author_name=stored.author_name,
            content=stored.content,
            timestamp=stored.timestamp,
        )
