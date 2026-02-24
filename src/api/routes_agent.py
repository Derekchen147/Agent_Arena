"""Agent 相关路由：查询、接入新 Agent、更新配置、管理工作目录与按技能搜索。

所有接口通过 app_state 获取 registry / workspace_manager，避免在 main 里循环依赖。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.models.agent import AgentProfile, CliConfig, ResponseConfig

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ── 请求模型 ──

class OnboardAgentRequest(BaseModel):
    """接入新 Agent 的请求体：ID、名称、仓库、角色提示、技能、CLI 类型等。"""
    agent_id: str
    name: str
    repo_url: str = ""               # Git 仓库 URL，留空则只创建空工作目录
    role_prompt: str = ""            # 角色描述，会写入工作目录下的 CLAUDE.md
    skills: list[str] = Field(default_factory=list)
    cli_type: str = "claude"         # claude / cursor / generic，决定用哪种 CLI 适配器
    avatar: str = ""
    priority_keywords: list[str] = Field(default_factory=list)


class UpdateAgentRequest(BaseModel):
    """更新 Agent 全部配置的请求体。"""
    name: str
    avatar: str = ""
    role_prompt: str = ""
    skills: list[str] = Field(default_factory=list)
    cli_type: str = "claude"
    command: str = ""
    timeout: int = 300
    extra_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    auto_respond: bool = True
    response_threshold: float = 0.6
    priority_keywords: list[str] = Field(default_factory=list)
    max_output_tokens: int = 2000


class UpdateWorkspaceConfigRequest(BaseModel):
    """写入 workspace 角色文件的请求体。"""
    content: str = ""


# ── 路由 ──

@router.get("")
async def list_agents():
    """获取所有已注册 Agent 的列表（从 registry 读取并序列化）。"""
    from src.main import app_state
    agents = app_state.registry.list_agents()
    return {"agents": [a.model_dump(mode="json") for a in agents]}


@router.post("/onboard")
async def onboard_agent(req: OnboardAgentRequest):
    """接入新 Agent：按 repo_url clone（或建空目录）、初始化工作区、写入配置并注册到 registry。"""
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


@router.post("/reload")
async def reload_agents():
    """从磁盘重新加载 agents 目录下的配置，更新内存中的 registry。"""
    from src.main import app_state
    app_state.registry.reload()
    return {"ok": True, "count": len(app_state.registry.agents)}


@router.get("/workspaces/list")
async def list_workspaces():
    """列出所有 Agent 工作目录及其状态（路径、是否就绪等）。"""
    from src.main import app_state
    return {"workspaces": app_state.workspace_manager.list_workspaces()}


@router.get("/search/skill")
async def search_by_skill(keyword: str):
    """按技能关键词在 registry 中搜索 Agent，返回匹配列表。"""
    from src.main import app_state
    agents = app_state.registry.find_by_skill(keyword)
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


@router.put("/{agent_id}")
async def update_agent(agent_id: str, req: UpdateAgentRequest):
    """更新 Agent 的全部配置：YAML、registry、workspace 角色文件。"""
    from src.main import app_state
    try:
        old_profile = app_state.registry.get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_profile = AgentProfile(
        agent_id=agent_id,
        name=req.name,
        avatar=req.avatar,
        workspace_dir=old_profile.workspace_dir,
        repo_url=old_profile.repo_url,
        role_prompt=req.role_prompt,
        skills=req.skills,
        response_config=ResponseConfig(
            auto_respond=req.auto_respond,
            response_threshold=req.response_threshold,
            priority_keywords=req.priority_keywords,
        ),
        cli_config=CliConfig(
            cli_type=req.cli_type,
            command=req.command,
            timeout=req.timeout,
            extra_args=req.extra_args,
            env=req.env,
        ),
        max_output_tokens=req.max_output_tokens,
    )

    try:
        updated = await app_state.workspace_manager.update_agent(new_profile, old_profile)
        return {"agent": updated.model_dump(mode="json")}
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


@router.get("/{agent_id}/workspace-config")
async def get_workspace_config(agent_id: str):
    """读取 Agent 的 workspace 角色文件（CLAUDE.md 或 role.mdc）。"""
    from src.main import app_state
    try:
        content, filename = app_state.workspace_manager.read_workspace_config(agent_id)
        return {"content": content, "filename": filename}
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")


@router.put("/{agent_id}/workspace-config")
async def update_workspace_config(agent_id: str, req: UpdateWorkspaceConfigRequest):
    """写入 Agent 的 workspace 角色文件。"""
    from src.main import app_state
    try:
        app_state.workspace_manager.write_workspace_config(agent_id, req.content)
        return {"ok": True}
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")
