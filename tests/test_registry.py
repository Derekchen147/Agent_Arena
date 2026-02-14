"""AgentRegistry 单元测试。"""

import pytest
from src.registry.agent_registry import AgentRegistry


@pytest.fixture
def registry():
    return AgentRegistry(config_dir="agents/")


def test_load_agents(registry):
    agents = registry.list_agents()
    assert len(agents) >= 4  # architect, developer, tester, compliance


def test_get_agent(registry):
    agent = registry.get_agent("architect")
    assert agent.name == "架构师"
    assert agent.cli_config.cli_type == "claude"
    assert agent.workspace_dir == "workspaces/architect"


def test_get_nonexistent_agent(registry):
    with pytest.raises(KeyError):
        registry.get_agent("nonexistent")


def test_find_by_skill(registry):
    results = registry.find_by_skill("架构")
    assert len(results) >= 1
    assert any(a.agent_id == "architect" for a in results)


def test_register_and_unregister(registry):
    from src.models.agent import AgentProfile
    profile = AgentProfile(agent_id="test_agent", name="测试Agent")
    registry.register_agent(profile)
    assert "test_agent" in registry.agents
    registry.unregister_agent("test_agent")
    assert "test_agent" not in registry.agents
