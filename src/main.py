"""Agent Arena：FastAPI 入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes_agent import router as agent_router
from src.api.routes_group import router as group_router
from src.api.routes_message import router as message_router
from src.api.websocket import WebSocketManager
from src.core.context_builder import ContextBuilder
from src.core.orchestrator import Orchestrator
from src.core.session_manager import SessionManager
from src.memory.store import MemoryStore
from src.registry.agent_registry import AgentRegistry
from src.worker.runtime import WorkerRuntime
from src.workspace.manager import WorkspaceManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """全局应用状态，持有所有核心组件的引用。"""

    session_manager: SessionManager
    registry: AgentRegistry
    memory_store: MemoryStore
    ws_manager: WebSocketManager
    context_builder: ContextBuilder
    worker_runtime: WorkerRuntime
    orchestrator: Orchestrator
    workspace_manager: WorkspaceManager


# 全局状态（供路由模块导入使用）
app_state: AppState = None  # type: ignore


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    global app_state

    logger.info("Starting Agent Arena...")

    # 初始化各组件
    session_manager = SessionManager(db_path="data/agent_arena.db")
    await session_manager.initialize()

    registry = AgentRegistry(config_dir="agents/")
    memory_store = MemoryStore(memory_dir="data/memory")
    ws_manager = WebSocketManager()
    workspace_manager = WorkspaceManager(
        registry=registry,
        workspaces_dir="workspaces",
        agents_config_dir="agents",
    )

    context_builder = ContextBuilder(
        session_manager=session_manager,
        registry=registry,
        memory_store=memory_store,
    )
    worker_runtime = WorkerRuntime(registry=registry, ws_manager=ws_manager)
    orchestrator = Orchestrator(
        session_manager=session_manager,
        context_builder=context_builder,
        worker_runtime=worker_runtime,
        registry=registry,
        ws_manager=ws_manager,
    )

    app_state = AppState(
        session_manager=session_manager,
        registry=registry,
        memory_store=memory_store,
        ws_manager=ws_manager,
        context_builder=context_builder,
        worker_runtime=worker_runtime,
        orchestrator=orchestrator,
        workspace_manager=workspace_manager,
    )

    agent_count = len(registry.agents)
    logger.info(f"Agent Arena started. {agent_count} agents loaded.")

    yield

    logger.info("Shutting down Agent Arena...")
    await worker_runtime.shutdown()
    await session_manager.close()


app = FastAPI(
    title="Agent Arena",
    description="Multi-AI Agent Collaboration Platform — CLI-based, workspace-driven",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(group_router)
app.include_router(message_router)
app.include_router(agent_router)


@app.get("/")
async def root():
    return {"name": "Agent Arena", "version": "0.1.0", "status": "running"}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "agents_loaded": len(app_state.registry.agents) if app_state else 0,
    }


@app.websocket("/ws/{group_id}")
async def websocket_endpoint(websocket: WebSocket, group_id: str):
    await app_state.ws_manager.connect(websocket, group_id)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "send_message":
                await app_state.session_manager.save_message(
                    group_id=group_id,
                    author_id=data.get("author_id", "human"),
                    content=data.get("content", ""),
                    author_type="human",
                    author_name=data.get("author_name", "用户"),
                    mentions=data.get("mentions", []),
                )
                await app_state.orchestrator.on_new_message(
                    group_id=group_id,
                    message_content=data.get("content", ""),
                    author_id=data.get("author_id", "human"),
                    mentions=data.get("mentions", []),
                )
    except WebSocketDisconnect:
        await app_state.ws_manager.disconnect(websocket, group_id)
