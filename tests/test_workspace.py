"""WorkspaceManager 单元测试。"""

import pytest
from pathlib import Path
from src.registry.agent_registry import AgentRegistry
from src.workspace.manager import WorkspaceManager


@pytest.fixture
def workspace_env(tmp_path):
    """创建临时工作环境。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    workspaces_dir = tmp_path / "workspaces"
    workspaces_dir.mkdir()

    registry = AgentRegistry(config_dir=str(agents_dir))  # 空注册表
    manager = WorkspaceManager(
        registry=registry,
        workspaces_dir=str(workspaces_dir),
        agents_config_dir=str(agents_dir),
    )
    return manager, registry, workspaces_dir, agents_dir


async def test_onboard_agent_no_repo(workspace_env):
    """测试接入新 Agent（无 git 仓库）。"""
    manager, registry, workspaces_dir, agents_dir = workspace_env

    profile = await manager.onboard_agent(
        agent_id="test_dev",
        name="测试开发",
        role_prompt="你是一个测试开发工程师",
        skills=["开发", "测试"],
        avatar="🧑‍💻",
    )

    # 验证工作目录已创建
    workspace = workspaces_dir / "test_dev"
    assert workspace.exists()

    # 验证 CLAUDE.md 已写入
    claude_md = workspace / "CLAUDE.md"
    assert claude_md.exists()
    assert "测试开发工程师" in claude_md.read_text(encoding="utf-8")

    # 验证已注册
    assert "test_dev" in registry.agents
    assert registry.get_agent("test_dev").name == "测试开发"

    # 验证 YAML 已保存
    yaml_path = agents_dir / "test_dev.yaml"
    assert yaml_path.exists()


async def test_remove_agent(workspace_env):
    """测试移除 Agent。"""
    manager, registry, workspaces_dir, agents_dir = workspace_env

    await manager.onboard_agent(agent_id="to_remove", name="要移除的")
    assert "to_remove" in registry.agents

    await manager.remove_agent("to_remove", delete_workspace=True)
    assert "to_remove" not in registry.agents
    assert not (workspaces_dir / "to_remove").exists()


async def test_list_workspaces(workspace_env):
    """测试列出工作目录。"""
    manager, registry, workspaces_dir, agents_dir = workspace_env

    await manager.onboard_agent(agent_id="agent_a", name="Agent A")
    await manager.onboard_agent(agent_id="agent_b", name="Agent B")

    workspaces = manager.list_workspaces()
    assert len(workspaces) == 2
    agent_ids = [w["agent_id"] for w in workspaces]
    assert "agent_a" in agent_ids
    assert "agent_b" in agent_ids
