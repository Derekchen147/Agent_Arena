"""员工相关路由：查询、接入新 Agent、管理工作目录。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ── 请求模型 ──

class OnboardAgentRequest(BaseModel):
    """接入新 Agent 的请求。"""
    agent_id: str
    name: str
    repo_url: str = ""               # Git 仓库 URL，留空则创建空工作目录
    role_prompt: str = ""             # 角色描述，会写入 CLAUDE.md
    skills: list[str] = Field(default_factory=list)
    cli_type: str = "claude"          # claude / generic
    avatar: str = ""
    priority_keywords: list[str] = Field(default_factory=list)


# ── 路由 ──

@router.get("")
async def list_agents():
    """获取所有已注册的 Agent 列表。"""
    from src.main import app_state
    agents = app_state.registry.list_agents()
    return {"agents": [a.model_dump(mode="json") for a in agents]}


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """获取 Agent 详情。"""
    from src.main import app_state
    try:
        agent = app_state.registry.get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"agent": agent.model_dump(mode="json")}


@router.post("/onboard")
async def onboard_agent(req: OnboardAgentRequest):
    """接入新 Agent：clone 仓库 + 初始化工作目录 + 注册。"""
    from src.main import app_state
    try:
        profile = await app_state.workspace_manager.onboard_agent(
            agent_id=req.agent_id,
            name=req.name,
            repo_url=req.repo_url,
            role_prompt=req.role_prompt,
            skills=req.skills,
            cli_type=req.cli_type,
            avatar=req.avatar,
            priority_keywords=req.priority_keywords,
        )
        return {"agent": profile.model_dump(mode="json")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{agent_id}")
async def remove_agent(agent_id: str, delete_workspace: bool = False):
    """移除 Agent（可选删除工作目录）。"""
    from src.main import app_state
    try:
        await app_state.workspace_manager.remove_agent(agent_id, delete_workspace)
        return {"ok": True}
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")


@router.post("/{agent_id}/update")
async def update_agent_workspace(agent_id: str):
    """更新 Agent 的工作目录（git pull）。"""
    from src.main import app_state
    try:
        await app_state.workspace_manager.update_workspace(agent_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces/list")
async def list_workspaces():
    """列出所有工作目录及其状态。"""
    from src.main import app_state
    return {"workspaces": app_state.workspace_manager.list_workspaces()}


@router.get("/search/skill")
async def search_by_skill(keyword: str):
    """按技能关键词搜索 Agent。"""
    from src.main import app_state
    agents = app_state.registry.find_by_skill(keyword)
    return {"agents": [a.model_dump(mode="json") for a in agents]}


@router.post("/reload")
async def reload_agents():
    """重新加载 Agent 配置。"""
    from src.main import app_state
    app_state.registry.reload()
    return {"ok": True, "count": len(app_state.registry.agents)}
