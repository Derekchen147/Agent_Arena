"""消息相关路由。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/messages", tags=["messages"])


class SendMessageRequest(BaseModel):
    group_id: str
    content: str
    author_id: str = "human"
    author_name: str = "用户"
    mentions: list[str] = Field(default_factory=list)


@router.get("/{group_id}")
async def get_messages(group_id: str, limit: int = 50, before: str | None = None):
    """获取群组消息历史。"""
    from src.main import app_state
    messages = await app_state.session_manager.get_messages(
        group_id, limit=limit, before=before
    )
    return {"messages": [m.model_dump(mode="json") for m in messages]}


@router.post("/send")
async def send_message(req: SendMessageRequest):
    """发送消息并触发编排引擎。"""
    from src.main import app_state

    # 1. 保存人类消息
    stored = await app_state.session_manager.save_message(
        group_id=req.group_id,
        author_id=req.author_id,
        content=req.content,
        author_type="human",
        author_name=req.author_name,
        mentions=req.mentions,
    )

    # 2. 通过 WebSocket 广播人类消息
    await app_state.ws_manager.broadcast_message(req.group_id, {
        "type": "user_message",
        "message": stored.model_dump(mode="json"),
    })

    # 3. 异步触发编排引擎（不阻塞 HTTP 响应）
    asyncio.create_task(
        app_state.orchestrator.on_new_message(
            group_id=req.group_id,
            message_content=req.content,
            author_id=req.author_id,
            mentions=req.mentions,
        )
    )

    return {"message": stored.model_dump(mode="json"), "status": "processing"}
