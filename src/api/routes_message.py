"""消息相关路由：获取群组历史消息、发送消息并触发编排。

发送消息时会先落库、再 WebSocket 广播、最后异步触发 on_new_message，不阻塞响应。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/messages", tags=["messages"])
logger = logging.getLogger(__name__)


class SendMessageRequest(BaseModel):
    """发送消息的请求体：群组、内容、作者信息与 @mentions。"""
    group_id: str
    content: str
    author_id: str = "human"
    author_name: str = "用户"
    mentions: list[str] = Field(default_factory=list)


@router.get("/{group_id}")
async def get_messages(group_id: str, limit: int = 50, before: str | None = None):
    """分页获取指定群组的消息历史；before 为游标（某条消息的 timestamp）。"""
    from src.main import app_state
    messages = await app_state.session_manager.get_messages(
        group_id, limit=limit, before=before
    )
    return {"messages": [m.model_dump(mode="json") for m in messages]}


@router.post("/send")
async def send_message(req: SendMessageRequest):
    """发送一条人类消息：落库 → WebSocket 广播 → 异步触发编排（Agent 回复在后台进行）。"""
    from src.main import app_state

    logger.info(
        "[CALL] API send_message: group_id=%s author_id=%s content_len=%d mentions=%s",
        req.group_id,
        req.author_id,
        len(req.content),
        req.mentions,
    )
    # 将人类消息写入 messages 表，得到 StoredMessage
    stored = await app_state.session_manager.save_message(
        group_id=req.group_id,
        author_id=req.author_id,
        content=req.content,
        author_type="human",
        author_name=req.author_name,
        mentions=req.mentions,
    )

    # 实时推送给该群所有 WebSocket 连接，前端可立即展示
    await app_state.ws_manager.broadcast_message(req.group_id, {
        "type": "user_message",
        "message": stored.model_dump(mode="json"),
    })

    # 不等待编排完成，直接返回；编排在后台执行并会再次通过 WS 推送 Agent 回复
    logger.info("[CALL] API send_message: triggering orchestrator.on_new_message (async)")
    asyncio.create_task(
        app_state.orchestrator.on_new_message(
            group_id=req.group_id,
            message_content=req.content,
            author_id=req.author_id,
            mentions=req.mentions,
        )
    )

    return {"message": stored.model_dump(mode="json"), "status": "processing"}


@router.get("/logs/{group_id}")
async def get_call_logs(group_id: str):
    """获取指定群聊会话的所有调用日志（最新在前）。"""
    from src.main import app_state
    if not hasattr(app_state, 'call_logger') or not app_state.call_logger:
        return {"logs": []}
    logs = app_state.call_logger.get_session_logs(group_id)
    return {"logs": [log.model_dump(mode="json") for log in logs]}
