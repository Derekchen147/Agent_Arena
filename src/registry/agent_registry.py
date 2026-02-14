"""Agent 注册表：从 agents 目录的 YAML 加载配置，支持动态注册、按技能搜索与重载。

编排与工作区等模块通过 registry 获取 Agent 元数据与工作目录路径。
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from src.models.agent import AgentProfile, CliConfig, ResponseConfig

logger = logging.getLogger(__name__)


class AgentRegistry:
    """内存中的 Agent 配置表：agent_id -> AgentProfile，支持从目录加载与重载。"""

    def __init__(self, config_dir: str = "agents/"):
        """指定配置目录并立即从该目录加载所有 *.yaml。"""
        self.agents: dict[str, AgentProfile] = {}
        self.config_dir = config_dir
        self._load_from_dir(config_dir)

    def _load_from_dir(self, config_dir: str) -> None:
        """遍历目录下所有 .yaml 文件，解析为 AgentProfile 并写入 self.agents。"""
        config_path = Path(config_dir)
        if not config_path.exists():
            logger.warning(f"Agent config directory not found: {config_dir}")
            return

        for file in config_path.glob("*.yaml"):
            try:
                profile = self._load_profile(file)
                self.agents[profile.agent_id] = profile
                logger.info(f"Loaded agent: {profile.agent_id} ({profile.name}) -> {profile.workspace_dir}")
            except Exception as e:
                logger.error(f"Failed to load agent from {file}: {e}")

    def _load_profile(self, file: Path) -> AgentProfile:
        """读取单个 YAML 文件，解析 response_config / cli_config 并构造 AgentProfile。"""
        with open(file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        response_config = ResponseConfig(**(data.get("response_config", {})))
        cli_config = CliConfig(**(data.get("cli_config", {})))

        return AgentProfile(
            agent_id=data["agent_id"],
            name=data.get("name", ""),
            avatar=data.get("avatar", ""),
            workspace_dir=data.get("workspace_dir", ""),
            repo_url=data.get("repo_url", ""),
            role_prompt=data.get("role_prompt", ""),
            skills=data.get("skills", []),
            response_config=response_config,
            cli_config=cli_config,
            max_output_tokens=data.get("max_output_tokens", 2000),
        )

    def register_agent(self, profile: AgentProfile) -> None:
        """将一名 Agent 加入注册表（如 onboard 完成后）；同 id 会覆盖。"""
        self.agents[profile.agent_id] = profile
        logger.info(f"Registered agent: {profile.agent_id} ({profile.name})")

    def unregister_agent(self, agent_id: str) -> None:
        """从注册表移除指定 Agent。"""
        if agent_id in self.agents:
            del self.agents[agent_id]
            logger.info(f"Unregistered agent: {agent_id}")

    def get_agent(self, agent_id: str) -> AgentProfile:
        """按 agent_id 获取档案；不存在则抛 KeyError。"""
        if agent_id not in self.agents:
            raise KeyError(f"Agent not found: {agent_id}")
        return self.agents[agent_id]

    def list_agents(self) -> list[AgentProfile]:
        """返回当前所有已注册 Agent 的列表。"""
        return list(self.agents.values())

    def find_by_skill(self, keyword: str) -> list[AgentProfile]:
        """按技能关键词过滤：skills 中任一项包含 keyword 的 Agent。"""
        return [
            a for a in self.agents.values()
            if any(keyword in s for s in a.skills)
        ]

    def reload(self) -> None:
        """清空当前表并从 config_dir 重新加载所有 YAML。"""
        self.agents.clear()
        self._load_from_dir(self.config_dir)
