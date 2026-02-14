"""AgentRegistry：员工与技能注册表，从 YAML 文件加载配置。"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from src.models.agent import AgentProfile, CliConfig, ResponseConfig

logger = logging.getLogger(__name__)


class AgentRegistry:
    """员工与技能注册表。"""

    def __init__(self, config_dir: str = "agents/"):
        self.agents: dict[str, AgentProfile] = {}
        self.config_dir = config_dir
        self._load_from_dir(config_dir)

    def _load_from_dir(self, config_dir: str) -> None:
        """从 YAML 文件批量加载员工配置。"""
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
        """从单个 YAML 文件加载 AgentProfile。"""
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
        """动态注册一个新 Agent（用于 clone 完仓库后注册）。"""
        self.agents[profile.agent_id] = profile
        logger.info(f"Registered agent: {profile.agent_id} ({profile.name})")

    def unregister_agent(self, agent_id: str) -> None:
        """注销一个 Agent。"""
        if agent_id in self.agents:
            del self.agents[agent_id]
            logger.info(f"Unregistered agent: {agent_id}")

    def get_agent(self, agent_id: str) -> AgentProfile:
        if agent_id not in self.agents:
            raise KeyError(f"Agent not found: {agent_id}")
        return self.agents[agent_id]

    def list_agents(self) -> list[AgentProfile]:
        return list(self.agents.values())

    def find_by_skill(self, keyword: str) -> list[AgentProfile]:
        return [
            a for a in self.agents.values()
            if any(keyword in s for s in a.skills)
        ]

    def reload(self) -> None:
        self.agents.clear()
        self._load_from_dir(self.config_dir)
