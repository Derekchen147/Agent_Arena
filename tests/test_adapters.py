"""CLI Adapter 基础测试。"""

import pytest
from src.worker.adapters.base import BaseAdapter
from src.worker.adapters.claude_cli import ClaudeCliAdapter
from src.worker.adapters.generic_cli import GenericCliAdapter
from src.models.protocol import AgentInput, Message


def test_adapter_registry():
    """验证 Adapter 子类实现了所有抽象方法。"""
    for cls in [ClaudeCliAdapter, GenericCliAdapter]:
        assert issubclass(cls, BaseAdapter)
        instance = cls()
        assert hasattr(instance, "invoke")
        assert hasattr(instance, "health_check")


def test_claude_cli_build_prompt():
    """测试 Claude CLI Adapter 的 prompt 构建。"""
    adapter = ClaudeCliAdapter()
    input = AgentInput(
        session_id="test",
        turn_id="t1",
        agent_id="architect",
        role_prompt="你是架构师",
        messages=[
            Message(role="user", author_name="用户", content="帮我设计一个系统"),
            Message(role="assistant", author_name="架构师", content="好的，我来分析"),
        ],
    )
    prompt = adapter._build_prompt(input)
    assert "用户" in prompt
    assert "帮我设计一个系统" in prompt
    # role_prompt 不应该出现在 prompt 中（它在 CLAUDE.md 里）
    assert "你是架构师" not in prompt


def test_claude_cli_parse_output():
    """测试 Claude CLI Adapter 的输出解析。"""
    adapter = ClaudeCliAdapter()
    input = AgentInput(session_id="test", turn_id="t1", agent_id="test")

    # 测试 next_mentions 解析
    content = '方案如下：...\n<!--NEXT_MENTIONS:["developer","tester"]-->'
    output = adapter._parse_output(content, input)
    assert output.next_mentions == ["developer", "tester"]
    assert "NEXT_MENTIONS" not in output.content

    # 测试 SKIP 标记
    content = "SKIP"
    output = adapter._parse_output(content, input)
    assert output.should_respond is False

    # 测试正常文本
    content = "这是一段正常回复"
    output = adapter._parse_output(content, input)
    assert output.should_respond is True
    assert output.content == "这是一段正常回复"
