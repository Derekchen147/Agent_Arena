"""BaseAdapter：所有 CLI Adapter 的抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

from src.models.protocol import AgentInput, AgentOutput

if TYPE_CHECKING:
    from src.mcp.loader import McpConfig
    from src.skills.loader import SkillDefinition


class BaseAdapter(ABC):
    """所有 CLI Adapter 的基类。

    每个 Adapter 负责：
    1. 在 Agent 的 workspace_dir 中启动 CLI 进程
    2. 把 AgentInput 转为 CLI 的输入
    3. 把 CLI 的输出解析为 AgentOutput
    """

    # 运行时注入的 MCP 配置和技能定义
    mcp_config: McpConfig | None = None
    skill_definitions: list[SkillDefinition] = []

    @abstractmethod
    async def invoke(
        self,
        input: AgentInput,
        workspace_dir: str,
        stream_callback: Callable[[str], None] | None = None,
    ) -> AgentOutput:
        """在指定工作目录中调用 CLI，返回结果。"""
        ...

    @abstractmethod
    async def health_check(self, workspace_dir: str) -> bool:
        """检查底层 CLI 是否可用。"""
        ...

    def _build_context_prompt(self, input: AgentInput) -> str:
        """构造动态上下文 prompt（由各个 CLI adapter 共享）。

        结构：
        1. 当前会话成员      — 让 Agent 知道自己是谁、群里有哪些同事可协作
        2. 早期对话摘要      — 较早消息的压缩摘要（长度受控）
        3. 最近对话          — 最后 N 条消息（通常 5 条）
        4. 技能列表          — 注入可用技能
        5. 相关记忆          — 如果有相关记忆片段
        6. 当前待回复消息    — 最后一条消息
        7. 协作提及格式      — 告诉 Agent 如何提及其他同事

        注：SOUL.md / AGENTS.md / USER.md 应由 CLI 自动从工作目录加载，
            不在此 prompt 中重复包含。
        """
        parts: list[str] = []

        # ── 1. 当前会话成员 ──
        agent_label = f"「{input.agent_name}」({input.agent_id})" if input.agent_name else f"({input.agent_id})"
        parts.append(f"## 当前会话成员\n你是{agent_label}。")
        if input.peers:
            parts.append("以下是本群的其他成员：")
            for p in input.peers:
                skills = ", ".join(p.skills) if p.skills else "无"
                parts.append(f"- {p.name} ({p.agent_id}) — 技能: {skills}")
        parts.append("")

        # ── 2. 早期对话摘要（如有） ──
        if input.conversation_summary:
            parts.append(input.conversation_summary)
            parts.append("")

        # ── 3. 最近对话 ──
        if input.messages and len(input.messages) > 1:
            recent = input.messages[:-1]
            parts.append("## 最近对话（只读上下文，不要重复回复这些消息）")
            for msg in recent:
                author = msg.author_name or msg.role
                parts.append(f"[{author}]: {msg.content}")
            parts.append("")

        # ── 4. 技能列表 ──
        if self.skill_definitions:
            from src.skills.loader import build_skills_prompt_section
            skills_section = build_skills_prompt_section(self.skill_definitions)
            if skills_section:
                parts.append(skills_section)

        # ── 5. 相关记忆 ──
        if input.memory_context:
            parts.append(f"## 相关记忆\n{input.memory_context}\n")

        # ── 6. 当前待回复消息 ──
        if input.messages:
            current = input.messages[-1]
            author = current.author_name or current.role
            parts.append("---\n## 当前待回复消息")
            parts.append(f"发送者: {author}")
            parts.append(f"内容:\n{current.content}\n---\n")

        # ── 7. 协作与提及格式 ──
        parts.append("## 协作与提及 (Collaboration)")
        parts.append("如果你需要其他同事参与接龙或处理任务，请在回复的最末尾使用以下格式：")
        parts.append("`<!--NEXT_MENTIONS:[\"agent_id_1\", \"agent_id_2\"]-->`")
        parts.append("(注意：agent_id 必须来自上方的「当前会话成员」列表)")

        return "\n".join(parts)
