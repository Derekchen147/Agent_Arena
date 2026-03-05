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

    def __init__(self, workspaces_dir: str = "workspaces/"):
        """扫描 workspaces 目录并从每个子目录加载 agent.yaml + SOUL.md。"""
        self.agents: dict[str, AgentProfile] = {}
        self.workspaces_dir = workspaces_dir
        self._load_from_workspaces(workspaces_dir)

    def _load_from_workspaces(self, workspaces_dir: str) -> None:
        """遍历 workspaces 目录下所有子目录，尝试从每个子目录加载 AgentProfile。"""
        workspaces_path = Path(workspaces_dir)
        if not workspaces_path.exists():
            logger.warning(f"Workspaces directory not found: {workspaces_dir}")
            return

        for subdir in workspaces_path.iterdir():
            if not subdir.is_dir():
                continue
            # 跳过软删除的 trash 目录
            if subdir.name == "trash":
                continue

            agent_yaml = subdir / "agent.yaml"
            if not agent_yaml.exists():
                continue

            try:
                profile = AgentProfile.from_workspace(subdir)
                self.agents[profile.agent_id] = profile
                logger.info(f"Loaded agent from workspace: {profile.agent_id} ({profile.name})")
            except Exception as e:
                logger.error(f"Failed to load agent from workspace {subdir}: {e}")

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
        """清空当前表并重新从 workspaces 目录扫描加载。"""
        self.agents.clear()
        self._load_from_workspaces(self.workspaces_dir)
