"""认证模块数据存储层"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import aiosqlite

from src.auth.models import UserInfo


class AuthStorage:
    """认证数据存储类，负责用户信息的持久化"""

    def __init__(self, db_path: str = "data/agent_arena.db"):
        """指定SQLite数据库文件路径"""
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """连接数据库并创建表"""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                username TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                avatar TEXT,
                token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                login_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS auth_states (
                state TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        await self._db.commit()

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            await self._db.close()

    async def save_user(self, user_info: UserInfo) -> None:
        """保存或更新用户信息"""
        now = datetime.now().isoformat()

        await self._db.execute(
            """
            INSERT OR REPLACE INTO users (
                id, account_id, username, email, phone, avatar,
                token, refresh_token,login_type,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                str(uuid.uuid4()),
                user_info.account_id,
                user_info.username,
                user_info.email,
                user_info.phone,
                user_info.avatar,
                user_info.token,
                user_info.refresh_token,
                user_info.login_type.value,
                user_info.created_at.isoformat() if user_info.created_at else now,
                now,
            ),
        )
        await self._db.commit()

    async def get_user(self) -> UserInfo | None:
        """获取当前登录用户（只支持单用户）"""
        cursor = await self._db.execute("SELECT * FROM users LIMIT 1")
        row = await cursor.fetchone()

        if not row:
            return None

        return UserInfo(
            account_id=row["account_id"],
            username=row["username"],
            email=row["email"],
            phone=row["phone"],
            avatar=row["avatar"],
            token=row["token"],
            refresh_token=row["refresh_token"],
            login_type=row["login_type"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def delete_user(self) -> None:
        """删除当前用户信息"""
        await self._db.execute("DELETE FROM users")
        await self._db.commit()

    async def update_token(self, token: str, refresh_token: str) -> None:
        """更新用户的token"""
        now = datetime.now().isoformat()
        await self._db.execute(
            """
            UPDATE users SET token = ?, refresh_token = ?, updated_at = ?
        """,
            (token, refresh_token, now),
        )
        await self._db.commit()

    async def save_auth_state(self, state: str, expires_in_seconds: int = 300) -> None:
        """保存认证状态"""
        now = datetime.now().isoformat()
        expires_at = datetime.fromisoformat(now).timestamp() + expires_in_seconds
        await self._db.execute(
            """
            INSERT OR REPLACE INTO auth_states (state, created_at, expires_at)
            VALUES (?, ?, ?)
        """,
            (state, now, str(expires_at)),
        )
        await self._db.commit()

    async def get_auth_state(self, state: str) -> bool:
        """检查认证状态是否存在且未过期"""
        cursor = await self._db.execute(
            "SELECT expires_at FROM auth_states WHERE state = ?",
            (state,),
        )
        row = await cursor.fetchone()

        if not row:
            return False

        expires_at = float(row["expires_at"])
        return datetime.now().timestamp() < expires_at

    async def delete_auth_state(self, state: str) -> None:
        """删除认证状态"""
        await self._db.execute("DELETE FROM auth_states WHERE state = ?", (state,))
        await self._db.commit()

    async def cleanup_expired_states(self) -> None:
        """清理过期的认证状态"""
        now = str(datetime.now().timestamp())
        await self._db.execute("DELETE FROM auth_states WHERE expires_at < ?", (now,))
        await self._db.commit()
