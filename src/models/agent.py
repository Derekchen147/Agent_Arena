"""Agent 配置模型：AgentProfile、ResponseConfig、CliConfig。

用于从 YAML 加载或 API 动态注册的 Agent 元数据，不包含运行时状态。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResponseConfig(BaseModel):
    """Agent 是否自动回复、相关性阈值及优先关键词（用于 may_reply 判断）。"""

    auto_respond: bool = True
    response_threshold: float = 0.6  # 相关性阈值 (0~1)
    priority_keywords: list[str] = Field(default_factory=list)


class CliConfig(BaseModel):
    """调用该 Agent 时使用的 CLI 类型、命令、超时与额外参数。"""

    cli_type: str = "claude"  # claude / cursor / generic
    command: str = ""         # generic 类型时的自定义启动命令
    timeout: int = 300        # 单次调用超时（秒）
    extra_args: list[str] = Field(default_factory=list)
    # 调用 CLI 时注入的环境变量（如代理）。会与当前进程环境合并，同名键以此为准。
    env: dict[str, str] = Field(default_factory=dict)


class AgentProfile(BaseModel):
    """Agent 档案：ID、名称、工作目录、角色提示、技能、响应与 CLI 配置。

    遵循 OpenClaw 风格：
    - 角色提示从 workspace_dir/SOUL.md 加载 (role_prompt)
    - 元数据从 workspace_dir/agent.yaml 加载 (name, avatar, skills, cli_config 等)
    - 运行指令从 workspace_dir/AGENTS.md 加载
    - 长期记忆在 workspace_dir/MEMORY.md
    """

    agent_id: str
    name: str = ""
    avatar: str = ""

    # 工作目录：Agent 的「地盘」，所有上下文和可操作文件都在这里
    workspace_dir: str = ""

    # 工作目录来源：如果是 git 仓库，填 clone URL
    repo_url: str = ""

    # 角色描述（从 SOUL.md 加载，不再直接从 YAML 加载）
    role_prompt: str = ""

    skills: list[str] = Field(default_factory=list)
    response_config: ResponseConfig = Field(default_factory=ResponseConfig)

    # CLI 配置
    cli_config: CliConfig = Field(default_factory=CliConfig)

    # Token 控制（用于上下文截断策略）
    max_output_tokens: int = 2000

    @classmethod
    def from_workspace(cls, workspace_path: str | Path) -> AgentProfile:
        """从工作目录加载 Agent 配置。

        1. 加载 agent.yaml 获取元数据
        2. 加载 SOUL.md 获取 role_prompt
        """
        import yaml
        from pathlib import Path

        path = Path(workspace_path)
        agent_yaml = path / "agent.yaml"
        soul_md = path / "SOUL.md"

        if not agent_yaml.exists():
            raise FileNotFoundError(f"agent.yaml not found in {workspace_path}")

        with open(agent_yaml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        role_prompt = ""
        if soul_md.exists():
            role_prompt = soul_md.read_text(encoding="utf-8").strip()

        # 合并数据
        return cls(
            agent_id=data.get("agent_id", path.name),
            name=data.get("name", ""),
            avatar=data.get("avatar", ""),
            workspace_dir=str(path.absolute()),
            repo_url=data.get("repo_url", ""),
            role_prompt=role_prompt,
            skills=data.get("skills", []),
            response_config=ResponseConfig(**data.get("response_config", {})),
            cli_config=CliConfig(**data.get("cli_config", {})),
            max_output_tokens=data.get("max_output_tokens", 2000),
        )
