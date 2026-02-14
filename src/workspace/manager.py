"""WorkspaceManager：管理 Agent 的工作目录。

核心流程：
1. 接入新 Agent → clone 其 GitHub 仓库到 workspaces/{agent_id}/
2. 写入 CLAUDE.md（角色描述/上下文）到工作目录
3. 生成 YAML 配置并注册到 AgentRegistry
4. Agent 就绑定了这个工作目录，CLI 在里面执行
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

import yaml

from src.models.agent import AgentProfile, CliConfig, ResponseConfig
from src.registry.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACES_DIR = "workspaces"
DEFAULT_AGENTS_DIR = "agents"


class WorkspaceManager:
    """管理 Agent 的工作目录和接入流程。"""

    def __init__(
        self,
        registry: AgentRegistry,
        workspaces_dir: str = DEFAULT_WORKSPACES_DIR,
        agents_config_dir: str = DEFAULT_AGENTS_DIR,
    ):
        self.registry = registry
        self.workspaces_dir = Path(workspaces_dir)
        self.agents_config_dir = Path(agents_config_dir)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)

    async def onboard_agent(
        self,
        agent_id: str,
        name: str,
        repo_url: str = "",
        role_prompt: str = "",
        skills: list[str] | None = None,
        cli_type: str = "claude",
        avatar: str = "",
        priority_keywords: list[str] | None = None,
    ) -> AgentProfile:
        """接入一个新的 AI 员工。

        完整流程：
        1. 如果有 repo_url，clone 到 workspaces/{agent_id}/
        2. 如果没有 repo_url，创建空的工作目录
        3. 写入 CLAUDE.md（角色上下文）
        4. 生成并保存 YAML 配置
        5. 注册到 AgentRegistry
        """
        workspace_path = self.workspaces_dir / agent_id

        # 1. 准备工作目录
        if repo_url:
            await self._clone_repo(repo_url, workspace_path)
        else:
            workspace_path.mkdir(parents=True, exist_ok=True)

        # 2. 写入 CLAUDE.md（Agent 的角色上下文）
        if role_prompt:
            self._write_claude_md(workspace_path, role_prompt)

        # 3. 构建 AgentProfile
        profile = AgentProfile(
            agent_id=agent_id,
            name=name,
            avatar=avatar,
            workspace_dir=str(workspace_path),
            repo_url=repo_url,
            role_prompt=role_prompt,
            skills=skills or [],
            response_config=ResponseConfig(
                priority_keywords=priority_keywords or [],
            ),
            cli_config=CliConfig(cli_type=cli_type),
        )

        # 4. 保存 YAML 配置
        self._save_agent_yaml(profile)

        # 5. 注册
        self.registry.register_agent(profile)

        logger.info(f"Onboarded agent: {agent_id} ({name}) -> {workspace_path}")
        return profile

    async def remove_agent(self, agent_id: str, delete_workspace: bool = False) -> None:
        """移除一个 Agent。"""
        # 注销注册
        self.registry.unregister_agent(agent_id)

        # 删除 YAML 配置
        yaml_path = self.agents_config_dir / f"{agent_id}.yaml"
        if yaml_path.exists():
            yaml_path.unlink()

        # 可选：删除工作目录
        if delete_workspace:
            workspace_path = self.workspaces_dir / agent_id
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
                logger.info(f"Deleted workspace: {workspace_path}")

        logger.info(f"Removed agent: {agent_id}")

    async def update_workspace(self, agent_id: str) -> None:
        """更新 Agent 的工作目录（git pull）。"""
        profile = self.registry.get_agent(agent_id)
        workspace_path = Path(profile.workspace_dir)

        if not workspace_path.exists():
            raise FileNotFoundError(f"Workspace not found: {workspace_path}")

        # 检查是否是 git 仓库
        git_dir = workspace_path / ".git"
        if git_dir.exists():
            process = await asyncio.create_subprocess_exec(
                "git", "pull",
                cwd=str(workspace_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(f"git pull failed: {stderr.decode()}")
            logger.info(f"Updated workspace for {agent_id}: {stdout.decode().strip()}")
        else:
            logger.warning(f"Workspace {workspace_path} is not a git repo, skip update")

    def list_workspaces(self) -> list[dict]:
        """列出所有工作目录及其状态。"""
        result = []
        if not self.workspaces_dir.exists():
            return result
        for d in self.workspaces_dir.iterdir():
            if d.is_dir():
                has_git = (d / ".git").exists()
                has_claude_md = (d / "CLAUDE.md").exists()
                result.append({
                    "agent_id": d.name,
                    "path": str(d),
                    "is_git_repo": has_git,
                    "has_claude_md": has_claude_md,
                    "registered": d.name in self.registry.agents,
                })
        return result

    async def _clone_repo(self, repo_url: str, target_path: Path) -> None:
        """Clone 一个 Git 仓库。"""
        if target_path.exists():
            logger.warning(f"Workspace already exists: {target_path}, pulling instead")
            process = await asyncio.create_subprocess_exec(
                "git", "pull",
                cwd=str(target_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            return

        logger.info(f"Cloning {repo_url} -> {target_path}")
        process = await asyncio.create_subprocess_exec(
            "git", "clone", repo_url, str(target_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"git clone failed: {stderr.decode()}")
        logger.info(f"Cloned successfully: {target_path}")

    def _write_claude_md(self, workspace_path: Path, role_prompt: str) -> None:
        """写入 CLAUDE.md 到工作目录（Claude CLI 会自动读取）。"""
        claude_md = workspace_path / "CLAUDE.md"
        # 如果已经存在 CLAUDE.md（比如仓库里自带的），不覆盖
        if claude_md.exists():
            logger.info(f"CLAUDE.md already exists in {workspace_path}, skipping write")
            return
        claude_md.write_text(role_prompt, encoding="utf-8")
        logger.info(f"Wrote CLAUDE.md to {workspace_path}")

    def _save_agent_yaml(self, profile: AgentProfile) -> None:
        """将 AgentProfile 保存为 YAML 文件。"""
        self.agents_config_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = self.agents_config_dir / f"{profile.agent_id}.yaml"

        data = {
            "agent_id": profile.agent_id,
            "name": profile.name,
            "avatar": profile.avatar,
            "workspace_dir": profile.workspace_dir,
            "repo_url": profile.repo_url,
            "role_prompt": profile.role_prompt,
            "skills": profile.skills,
            "response_config": profile.response_config.model_dump(),
            "cli_config": profile.cli_config.model_dump(),
            "max_output_tokens": profile.max_output_tokens,
        }

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        logger.info(f"Saved agent config: {yaml_path}")
