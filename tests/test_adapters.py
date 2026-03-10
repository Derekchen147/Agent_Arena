"""CLI Adapter 基础测试。"""

import pytest
from src.worker.adapters.base import BaseAdapter
from src.worker.adapters.claude_cli import ClaudeCliAdapter
from src.worker.adapters.gemini_cli import GeminiCliAdapter
from src.worker.adapters.generic_cli import GenericCliAdapter
from src.worker.adapters.opencode_cli import OpencodeCliAdapter
from src.models.protocol import AgentInput, Message


def test_adapter_registry():
    """验证 Adapter 子类实现了所有抽象方法。"""
    for cls in [ClaudeCliAdapter, GeminiCliAdapter, GenericCliAdapter, OpencodeCliAdapter]:
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


def test_gemini_cli_build_prompt():
    """测试 Gemini CLI Adapter 的 prompt 构建。"""
    adapter = GeminiCliAdapter()
    input = AgentInput(
        session_id="test",
        turn_id="t1",
        agent_id="architect",
        messages=[
            Message(role="user", author_name="用户", content="帮我设计一个系统"),
        ],
    )
    prompt = adapter._build_prompt(input)
    assert "用户" in prompt
    assert "帮我设计一个系统" in prompt
    assert "<!--NEXT_MENTIONS:" in prompt


def test_gemini_cli_parse_output():
    """测试 Gemini CLI Adapter 的输出解析。"""
    adapter = GeminiCliAdapter()
    input = AgentInput(session_id="test", turn_id="t1", agent_id="test")

    # 测试 JSON 格式
    content = '{"result": "这是结果", "duration_ms": 100}'
    output = adapter._parse_output(content, input)
    assert output.content == "这是结果"

    # 测试 NDJSON 格式
    content = '{"type": "result", "result": "这是 NDJSON 结果"}'
    output = adapter._parse_output(content, input)
    assert output.content == "这是 NDJSON 结果"

    # 测试 NEXT_MENTIONS
    content = '结果如下<!--NEXT_MENTIONS:["dev"]-->'
    output = adapter._parse_output(content, input)
    assert output.next_mentions == ["dev"]


def test_opencode_cli_build_prompt():
    """测试 OpenCode CLI Adapter 的 prompt 构建。"""
    adapter = OpencodeCliAdapter()
    input = AgentInput(
        session_id="test",
        turn_id="t1",
        agent_id="architect",
        messages=[
            Message(role="user", author_name="用户", content="帮我设计一个系统"),
        ],
    )
    prompt = adapter._build_prompt(input)
    assert "用户" in prompt
    assert "帮我设计一个系统" in prompt
    assert "<!--NEXT_MENTIONS:" in prompt


def test_opencode_cli_parse_output():
    """测试 OpenCode CLI Adapter 的 NDJSON 输出解析。"""
    import json
    adapter = OpencodeCliAdapter()
    input = AgentInput(session_id="test", turn_id="t1", agent_id="test")

    # 测试标准 NDJSON 格式（多个 text 事件拼接）
    events = [
        {"type": "step_start", "sessionID": "ses_123", "part": {}},
        {"type": "text", "sessionID": "ses_123", "part": {"text": "Hello, "}},
        {"type": "text", "sessionID": "ses_123", "part": {"text": "world!"}},
        {"type": "step_finish", "sessionID": "ses_123", "part": {
            "reason": "stop", "cost": 0.001,
            "tokens": {"input": 100, "output": 20, "total": 120},
        }},
    ]
    raw = "\n".join(json.dumps(e) for e in events)
    output = adapter._parse_output(raw, input)
    assert output.content == "Hello, world!"
    assert output.execution_meta.input_tokens == 100
    assert output.execution_meta.output_tokens == 20
    assert output.execution_meta.cost_usd == 0.001
    assert output.execution_meta.cli_session_id == "ses_123"

    # 测试 NEXT_MENTIONS
    events2 = [
        {"type": "text", "sessionID": "ses_456", "part": {
            "text": '结果如下<!--NEXT_MENTIONS:["dev"]-->',
        }},
        {"type": "step_finish", "sessionID": "ses_456", "part": {
            "reason": "stop", "cost": 0,
            "tokens": {"input": 50, "output": 10, "total": 60},
        }},
    ]
    raw2 = "\n".join(json.dumps(e) for e in events2)
    output2 = adapter._parse_output(raw2, input)
    assert output2.next_mentions == ["dev"]
    assert "NEXT_MENTIONS" not in output2.content

    # 测试 SKIP
    events3 = [{"type": "text", "sessionID": "ses_789", "part": {"text": "SKIP"}}]
    raw3 = "\n".join(json.dumps(e) for e in events3)
    output3 = adapter._parse_output(raw3, input)
    assert output3.should_respond is False
