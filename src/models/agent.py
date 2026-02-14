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


class AgentProfile(BaseModel):
    """Agent 档案：ID、名称、工作目录、角色提示、技能、响应与 CLI 配置。

    工作目录（workspace_dir）即 Agent 的「地盘」，上下文与可操作文件均在此；
    可为 Git 仓库 clone 后的本地路径。
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
