"""Agent 配置模型：AgentProfile / ResponseConfig / CliConfig。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResponseConfig(BaseModel):
    """Agent 响应配置。"""

    auto_respond: bool = True
    response_threshold: float = 0.6  # 相关性阈值 (0~1)
    priority_keywords: list[str] = Field(default_factory=list)


class CliConfig(BaseModel):
    """CLI 调用配置。"""

    cli_type: str = "claude"  # claude / cursor / generic
    command: str = ""  # 自定义启动命令（generic 类型使用）
    timeout: int = 300  # 单次调用超时（秒）
    extra_args: list[str] = Field(default_factory=list)  # 额外 CLI 参数


class AgentProfile(BaseModel):
    """员工档案，从 YAML 文件加载。

    核心概念：每个 Agent 有一个自己的工作目录（workspace_dir），
    该目录就是 Agent 的「地盘」——上下文、配置、可修改的文件都在里面。
    实际运作时，工作目录可以是一个 GitHub 仓库 clone 下来的本地副本。
    """

    agent_id: str
    name: str = ""
    avatar: str = ""

    # 工作目录：Agent 的「地盘」，所有上下文和可操作文件都在这里
    workspace_dir: str = ""

    # 工作目录来源：如果是 git 仓库，填 clone URL
    repo_url: str = ""

    # 角色描述（会写入工作目录的配置文件，如 CLAUDE.md）
    role_prompt: str = ""

    skills: list[str] = Field(default_factory=list)
    response_config: ResponseConfig = Field(default_factory=ResponseConfig)

    # CLI 配置
    cli_config: CliConfig = Field(default_factory=CliConfig)

    # Token 控制（用于上下文截断策略）
    max_output_tokens: int = 2000
