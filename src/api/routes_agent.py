"""Agent 相关路由：查询、接入新 Agent、更新配置、管理工作目录与按技能搜索。

所有接口通过 app_state 获取 registry / workspace_manager，避免在 main 里循环依赖。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.models.agent import AgentProfile, CliConfig, ResponseConfig

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _agent_to_dict(profile: AgentProfile) -> dict:
    """将 AgentProfile 转为 JSON 可序列化的 dict，包含 skills 和 MCP 摘要。"""
    data = profile.model_dump(mode="json", exclude={"mcp_config", "skill_definitions"})

    # 技能摘要
    data["skill_definitions"] = [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
        }
        for s in (profile.skill_definitions or [])
    ]

    # MCP 摘要
    if profile.mcp_config and profile.mcp_config.servers:
        data["mcp_config"] = {
            "servers": [
                {
                    "server_id": srv.server_id,
                    "server_type": srv.server_type,
                    "transport": srv.transport,
                    "command": srv.command,
                    "args": srv.args,
                    "env": srv.env,
                    "required_env": srv.required_env,
                    "capability": srv.capability,
                }
                for srv in profile.mcp_config.servers
            ]
        }
    else:
        data["mcp_config"] = None

    return data


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


class UpdateOpenClawFileRequest(BaseModel):
    """更新 OpenClaw 文件的请求体。"""
    content: str


# ── 路由 ──

@router.get("/{agent_id}/openclaw/{filename}")
async def get_openclaw_file(agent_id: str, filename: str):
    """读取特定的 OpenClaw 文件（SOUL.md, AGENTS.md, USER.md）。"""
    from src.main import app_state
    try:
        content = app_state.workspace_manager.read_openclaw_file(agent_id, filename)
        return {"content": content, "filename": filename}
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")


@router.put("/{agent_id}/openclaw/{filename}")
async def update_openclaw_file(agent_id: str, filename: str, req: UpdateOpenClawFileRequest):
    """写入特定的 OpenClaw 文件。"""
    from src.main import app_state
    try:
        app_state.workspace_manager.write_openclaw_file(agent_id, filename, req.content)
        return {"ok": True}
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")

@router.get("")
async def list_agents():
    """获取所有已注册 Agent 的列表（从 registry 读取并序列化）。"""
    from src.main import app_state
    agents = app_state.registry.list_agents()
    return {"agents": [_agent_to_dict(a) for a in agents]}


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
        return {"agent": _agent_to_dict(profile)}
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
    return {"agents": [_agent_to_dict(a) for a in agents]}


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """获取 Agent 详情。"""
    from src.main import app_state
    try:
        agent = app_state.registry.get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"agent": _agent_to_dict(agent)}


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
        return {"agent": _agent_to_dict(updated)}
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


# ── Skills & MCP ──

@router.get("/{agent_id}/skills")
async def get_agent_skills(agent_id: str):
    """获取 Agent 的技能列表（从 workspace/skills/ 加载）。"""
    from src.main import app_state
    try:
        profile = app_state.registry.get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {
        "skills": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "body": s.body,
            }
            for s in (profile.skill_definitions or [])
        ]
    }


@router.get("/{agent_id}/mcp")
async def get_agent_mcp(agent_id: str):
    """获取 Agent 的 MCP 配置。"""
    from src.main import app_state
    try:
        profile = app_state.registry.get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not profile.mcp_config:
        return {"servers": [], "readiness": []}

    from src.mcp.loader import check_mcp_readiness
    env = profile.cli_config.env or {}
    readiness = check_mcp_readiness(profile.mcp_config, env)

    return {
        "servers": [
            {
                "server_id": srv.server_id,
                "server_type": srv.server_type,
                "transport": srv.transport,
                "command": srv.command,
                "args": srv.args,
                "env": srv.env,
                "required_env": srv.required_env,
                "capability": srv.capability,
            }
            for srv in profile.mcp_config.servers
        ],
        "readiness": readiness,
    }


class CreateSkillRequest(BaseModel):
    """创建新技能的请求。"""
    skill_id: str
    name: str = ""
    description: str = ""
    body: str = ""


class CreateMcpServerRequest(BaseModel):
    """添加 MCP 服务器的请求。"""
    server_id: str
    server_type: str = "external"
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    required_env: list[str] = Field(default_factory=list)
    capability: str = ""


class UpdateMcpEnvRequest(BaseModel):
    """更新 MCP 服务器环境变量的请求。"""
    server_id: str
    env: dict[str, str] = Field(default_factory=dict)


@router.put("/{agent_id}/mcp")
async def update_agent_mcp_env(agent_id: str, req: UpdateMcpEnvRequest):
    """更新 MCP 服务器的环境变量配置（写回 mcp_config.yaml）。"""
    from pathlib import Path

    import yaml

    from src.main import app_state

    try:
        profile = app_state.registry.get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")

    config_path = Path(profile.workspace_dir) / "mcp" / "mcp_config.yaml"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="MCP config not found")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # 找到对应 server 并更新 env
    updated = False
    for srv in data.get("mcp_servers", []):
        if srv.get("id") == req.server_id:
            srv["env"] = req.env
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail=f"MCP server '{req.server_id}' not found")

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 重新加载该 agent 的 MCP 配置
    from src.mcp.loader import load_mcp_config
    profile.mcp_config = load_mcp_config(profile.workspace_dir)

    return {"ok": True}


@router.post("/{agent_id}/skills")
async def create_skill(agent_id: str, req: CreateSkillRequest):
    """创建新技能：在 workspace/skills/{skill_id}/ 下写入 SKILL.md。"""
    from pathlib import Path

    from src.main import app_state
    from src.skills.loader import load_skills_from_workspace

    try:
        profile = app_state.registry.get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")

    skill_dir = Path(profile.workspace_dir) / "skills" / req.skill_id
    if skill_dir.exists():
        raise HTTPException(status_code=409, detail=f"Skill '{req.skill_id}' already exists")

    skill_dir.mkdir(parents=True)

    name = req.name or req.skill_id
    content = f"---\nname: {name}\ndescription: {req.description}\n---\n\n{req.body or f'# {name}'}\n"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    # 重新加载
    profile.skill_definitions = load_skills_from_workspace(profile.workspace_dir)

    return {"ok": True, "skill_id": req.skill_id}


@router.delete("/{agent_id}/skills/{skill_id}")
async def delete_skill(agent_id: str, skill_id: str):
    """删除技能：移除 workspace/skills/{skill_id}/ 目录。"""
    import shutil
    from pathlib import Path

    from src.main import app_state
    from src.skills.loader import load_skills_from_workspace

    try:
        profile = app_state.registry.get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")

    skill_dir = Path(profile.workspace_dir) / "skills" / skill_id
    if not skill_dir.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    shutil.rmtree(skill_dir)

    # 重新加载
    profile.skill_definitions = load_skills_from_workspace(profile.workspace_dir)

    return {"ok": True}


@router.post("/{agent_id}/mcp/servers")
async def add_mcp_server(agent_id: str, req: CreateMcpServerRequest):
    """添加 MCP 服务器到 mcp_config.yaml。"""
    from pathlib import Path

    import yaml

    from src.main import app_state
    from src.mcp.loader import load_mcp_config

    try:
        profile = app_state.registry.get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")

    mcp_dir = Path(profile.workspace_dir) / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    config_path = mcp_dir / "mcp_config.yaml"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    servers = data.setdefault("mcp_servers", [])

    # 检查重复
    for srv in servers:
        if srv.get("id") == req.server_id:
            raise HTTPException(status_code=409, detail=f"MCP server '{req.server_id}' already exists")

    new_srv: dict = {
        "id": req.server_id,
        "type": req.server_type,
        "transport": req.transport,
        "command": req.command,
        "args": req.args,
    }
    if req.env:
        new_srv["env"] = req.env
    if req.required_env:
        new_srv["required_env"] = req.required_env
    if req.capability:
        new_srv["capability"] = req.capability

    servers.append(new_srv)

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    profile.mcp_config = load_mcp_config(profile.workspace_dir)

    return {"ok": True, "server_id": req.server_id}


@router.delete("/{agent_id}/mcp/servers/{server_id}")
async def delete_mcp_server(agent_id: str, server_id: str):
    """从 mcp_config.yaml 中删除指定 MCP 服务器。"""
    from pathlib import Path

    import yaml

    from src.main import app_state
    from src.mcp.loader import load_mcp_config

    try:
        profile = app_state.registry.get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")

    config_path = Path(profile.workspace_dir) / "mcp" / "mcp_config.yaml"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="MCP config not found")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    servers = data.get("mcp_servers", [])
    original_len = len(servers)
    data["mcp_servers"] = [s for s in servers if s.get("id") != server_id]

    if len(data["mcp_servers"]) == original_len:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    profile.mcp_config = load_mcp_config(profile.workspace_dir)

    return {"ok": True}
