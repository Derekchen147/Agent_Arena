"""Agent Arena：FastAPI 入口。

本模块负责：
- 应用启动与生命周期（lifespan）
- 各核心组件的初始化与注入
- 注册路由、中间件与 WebSocket 端点
"""

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

# 配置根日志格式，便于排查问题
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """全局应用状态，持有所有核心组件的引用。

    供各路由模块通过 main.app_state 访问，避免循环依赖。
    """

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
    """应用生命周期管理：启动时初始化所有组件，关闭时释放资源。"""
    global app_state

    logger.info("Starting Agent Arena...")

    # 初始化数据层：会话与群组、消息的持久化
    session_manager = SessionManager(db_path="data/agent_arena.db")
    await session_manager.initialize()

    # 初始化 Agent 注册表、记忆存储、WebSocket 广播、工作区管理
    registry = AgentRegistry(config_dir="agents/")
    memory_store = MemoryStore(memory_dir="data/memory")
    ws_manager = WebSocketManager()
    workspace_manager = WorkspaceManager(
        registry=registry,
        workspaces_dir="workspaces",
        agents_config_dir="agents",
    )

    # 初始化上下文构建器与 Worker 运行时
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

    # 将各组件挂到全局状态，供路由与 WebSocket 使用
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

    # 关闭阶段：先停 Worker，再关闭数据库连接
    logger.info("Shutting down Agent Arena...")
    await worker_runtime.shutdown()
    await session_manager.close()


# 创建 FastAPI 应用并绑定生命周期
app = FastAPI(
    title="Agent Arena",
    description="Multi-AI Agent Collaboration Platform — CLI-based, workspace-driven",
    version="0.1.0",
    lifespan=lifespan,
)

# 允许跨域，便于前端或第三方调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载业务路由：群组、消息、Agent；顺序影响前缀与优先级
app.include_router(group_router)
app.include_router(message_router)
app.include_router(agent_router)


@app.get("/")
async def root():
    """根路径：返回应用名称、版本与运行状态。"""
    return {"name": "Agent Arena", "version": "0.1.0", "status": "running"}


@app.get("/api/health")
async def health():
    """健康检查：用于探活与监控，返回当前已加载的 Agent 数量。"""
    return {
        "status": "ok",
        "agents_loaded": len(app_state.registry.agents) if app_state else 0,
    }


@app.websocket("/ws/{group_id}")
async def websocket_endpoint(websocket: WebSocket, group_id: str):
    """WebSocket 入口：客户端连接后，接收 send_message 并落库、触发编排。"""
    await app_state.ws_manager.connect(websocket, group_id)
    try:
        while True:
            data = await websocket.receive_json()
            # 仅处理「发送消息」类型：先持久化，再交给编排器驱动 Agent 回复
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
