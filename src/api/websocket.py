"""WebSocket 管理：实时消息推送、员工状态更新。"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """管理所有 WebSocket 连接，提供广播和定向推送。"""

    def __init__(self):
        # group_id -> list of connections
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, group_id: str) -> None:
        """接受新的 WebSocket 连接。"""
        await websocket.accept()
        if group_id not in self.connections:
            self.connections[group_id] = []
        self.connections[group_id].append(websocket)
        logger.info(f"WebSocket connected to group {group_id}")

    async def disconnect(self, websocket: WebSocket, group_id: str) -> None:
        """断开 WebSocket 连接。"""
        if group_id in self.connections:
            self.connections[group_id] = [
                ws for ws in self.connections[group_id] if ws != websocket
            ]
            if not self.connections[group_id]:
                del self.connections[group_id]
        logger.info(f"WebSocket disconnected from group {group_id}")

    async def broadcast_message(self, group_id: str, data: dict[str, Any]) -> None:
        """向群组内所有连接广播消息。"""
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
        """向所有连接广播 Agent 状态更新。"""
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
