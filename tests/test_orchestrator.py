"""Orchestrator 单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.orchestrator import Orchestrator, Turn
from src.models.protocol import AgentOutput
from src.models.session import GroupConfig


@pytest.fixture
def mock_deps():
    session_manager = AsyncMock()
    context_builder = AsyncMock()
    worker_runtime = AsyncMock()
    registry = MagicMock()
    ws_manager = AsyncMock()

    mock_profile = MagicMock()
    mock_profile.name = "测试Agent"
    registry.get_agent.return_value = mock_profile

    return session_manager, context_builder, worker_runtime, registry, ws_manager


def test_parse_mentions(mock_deps):
    session_manager, context_builder, worker_runtime, registry, ws_manager = mock_deps
    orchestrator = Orchestrator(
        session_manager=session_manager,
        context_builder=context_builder,
        worker_runtime=worker_runtime,
        registry=registry,
        ws_manager=ws_manager,
    )

    agent_ids = ["architect", "developer", "tester"]

    mentions = orchestrator._parse_mentions("@architect 请设计方案", agent_ids)
    assert "architect" in mentions

    mentions = orchestrator._parse_mentions("@all 大家看看", agent_ids)
    assert "@all" in mentions


async def test_execute_turn_must_reply(mock_deps):
    session_manager, context_builder, worker_runtime, registry, ws_manager = mock_deps

    worker_runtime.invoke_agent.return_value = AgentOutput(
        content="测试回复", next_mentions=[], should_respond=True
    )

    orchestrator = Orchestrator(
        session_manager=session_manager,
        context_builder=context_builder,
        worker_runtime=worker_runtime,
        registry=registry,
        ws_manager=ws_manager,
    )

    turn = Turn(
        must_reply_agents=["architect"],
        may_reply_agents=[],
    )

    await orchestrator.execute_turn(turn, "test-group", GroupConfig())

    worker_runtime.invoke_agent.assert_called_once()
    session_manager.save_message.assert_called_once()
