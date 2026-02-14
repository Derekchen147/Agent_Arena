"""群组相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.models.session import GroupConfig

router = APIRouter(prefix="/api/groups", tags=["groups"])


# ── 请求/响应模型 ──

class CreateGroupRequest(BaseModel):
    name: str
    description: str = ""
    config: GroupConfig = Field(default_factory=GroupConfig)


class AddMemberRequest(BaseModel):
    agent_id: str
    display_name: str = ""
    role_in_group: str | None = None


# ── 路由 ──
# 注意：实际的 session_manager 依赖注入在 main.py 中配置

@router.get("")
async def list_groups():
    """获取所有群组列表。"""
    from src.main import app_state
    groups = await app_state.session_manager.list_groups()
    return {"groups": [g.model_dump(mode="json") for g in groups]}


@router.post("")
async def create_group(req: CreateGroupRequest):
    """创建新群组。"""
    from src.main import app_state
    group = await app_state.session_manager.create_group(
        name=req.name,
        description=req.description,
        config=req.config,
    )
    return {"group": group.model_dump(mode="json")}


@router.get("/{group_id}")
async def get_group(group_id: str):
    """获取群组详情。"""
    from src.main import app_state
    group = await app_state.session_manager.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"group": group.model_dump(mode="json")}


@router.delete("/{group_id}")
async def delete_group(group_id: str):
    """删除群组。"""
    from src.main import app_state
    await app_state.session_manager.delete_group(group_id)
    return {"ok": True}


@router.post("/{group_id}/members")
async def add_member(group_id: str, req: AddMemberRequest):
    """添加成员到群组。"""
    from src.main import app_state
    member = await app_state.session_manager.add_member(
        group_id=group_id,
        member_type="agent",
        agent_id=req.agent_id,
        display_name=req.display_name,
        role_in_group=req.role_in_group,
    )
    return {"member": member.model_dump(mode="json")}


@router.delete("/{group_id}/members/{member_id}")
async def remove_member(group_id: str, member_id: str):
    """从群组移除成员。"""
    from src.main import app_state
    await app_state.session_manager.remove_member(group_id, member_id)
    return {"ok": True}
