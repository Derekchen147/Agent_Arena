"""WebSocket 管理：按群组维护连接，提供群内广播与全局状态广播。

用于推送人类消息、Agent 回复、系统提示等；发送失败时自动从连接列表中移除。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """按 group_id 维护 WebSocket 连接列表，支持向某群广播或向所有连接广播。"""

    def __init__(self):
        """connections: group_id -> 该群当前所有 WebSocket 连接列表。"""
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, group_id: str) -> None:
        """接受新连接并加入对应群组列表；若该群尚无连接则先建列表。"""
        await websocket.accept()
        if group_id not in self.connections:
            self.connections[group_id] = []
        self.connections[group_id].append(websocket)
        logger.info(f"WebSocket connected to group {group_id}")

    async def disconnect(self, websocket: WebSocket, group_id: str) -> None:
        """将指定连接从该群列表中移除；若群内已无连接则删除该群键。"""
        if group_id in self.connections:
            self.connections[group_id] = [
                ws for ws in self.connections[group_id] if ws != websocket
            ]
            if not self.connections[group_id]:
                del self.connections[group_id]
        logger.info(f"WebSocket disconnected from group {group_id}")

    async def broadcast_message(self, group_id: str, data: dict[str, Any]) -> None:
        """向指定群组内所有连接广播一条 JSON 消息；发送失败的连接会被自动 disconnect。"""
        if group_id not in self.connections:
            return
        message = json.dumps(data, ensure_ascii=False, default=str)
        disconnected = []
        for ws in self.connections[group_id]:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            await self.disconnect(ws, group_id)

    async def broadcast_status(self, agent_id: str, data: dict[str, Any]) -> None:
        """向所有群的所有连接广播 Agent 状态更新（如忙碌/空闲）；失败连接会被移除。"""
        message = json.dumps(data, ensure_ascii=False, default=str)
        for group_id, connections in self.connections.items():
            disconnected = []
            for ws in connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                await self.disconnect(ws, group_id)
