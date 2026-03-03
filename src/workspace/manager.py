"""工作区管理：Agent 接入、工作目录创建、角色配置写入、YAML 持久化与注册表同步。

遵循 OpenClaw 风格：
- SOUL.md: 角色人设
- AGENTS.md: 运行规则与记忆管理
- agent.yaml: 元数据配置
- CLAUDE.md/GEMINI.md/.cursorrules: 引导 Agent 加载上述文件的指令
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

import yaml

from src.core.prompts import OPENCLAW_AGENTS_TEMPLATE, OPENCLAW_LOADING_INSTRUCTION, OPENCLAW_SOUL_TEMPLATE
from src.memory.personal import PersonalMemoryManager
from src.models.agent import AgentProfile, CliConfig, ResponseConfig
from src.registry.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACES_DIR = "workspaces"


class WorkspaceManager:
    """负责 Agent 工作目录的创建、clone、OpenClaw 配置写入、agent.yaml 持久化与 registry 注册。"""

    def __init__(
        self,
        registry: AgentRegistry,
        workspaces_dir: str = DEFAULT_WORKSPACES_DIR,
    ):
        """指定工作区根目录；工作区目录不存在时会创建。"""
        self.registry = registry
        self.workspaces_dir = Path(workspaces_dir)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self._personal_memory = PersonalMemoryManager()

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
        """接入一个新的 AI 员工。"""
        workspace_path = self.workspaces_dir / agent_id

        # 有 repo_url 则 clone 到 workspaces/{agent_id}，否则创建空目录
        if repo_url:
            await self._clone_repo(repo_url, workspace_path)
        else:
            workspace_path.mkdir(parents=True, exist_ok=True)

        # 1. 写入 SOUL.md
        soul_md = workspace_path / "SOUL.md"
        if role_prompt or not soul_md.exists():
            final_soul = OPENCLAW_SOUL_TEMPLATE
            if role_prompt:
                final_soul += f"\n\n## Custom Role\n\n{role_prompt}"
            soul_md.write_text(final_soul, encoding="utf-8")

        # 2. 写入 AGENTS.md
        agents_md = workspace_path / "AGENTS.md"
        if not agents_md.exists():
            agents_md.write_text(OPENCLAW_AGENTS_TEMPLATE, encoding="utf-8")

        # 3. 写入引导文件 (CLAUDE.md, etc.)
        self._write_loading_instructions(workspace_path, cli_type)

        # 4. 构造 AgentProfile
        profile = AgentProfile(
            agent_id=agent_id,
            name=name,
            avatar=avatar,
            workspace_dir=str(workspace_path.absolute()),
            repo_url=repo_url,
            role_prompt=role_prompt or (soul_md.read_text(encoding="utf-8") if soul_md.exists() else ""),
            skills=skills or [],
            response_config=ResponseConfig(
                priority_keywords=priority_keywords or [],
            ),
            cli_config=CliConfig(cli_type=cli_type),
        )

        # 5. 将配置写入 {workspace}/agent.yaml
        self._save_agent_yaml(profile)

        # 6. 注册到 AgentRegistry
        self.registry.register_agent(profile)

        # 7. 初始化个人记忆目录和 MEMORY.md 模板
        self._personal_memory.init_workspace_memory(str(workspace_path), name)

        logger.info(f"Onboarded agent: {agent_id} ({name}) -> {workspace_path}")
        return profile

    async def remove_agent(self, agent_id: str, delete_workspace: bool = False) -> None:
        """从注册表注销，并可选的删除工作目录。"""
        self.registry.unregister_agent(agent_id)

        if delete_workspace:
            workspace_path = self.workspaces_dir / agent_id
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
                logger.info(f"Deleted workspace: {workspace_path}")

        logger.info(f"Removed agent: {agent_id}")

    async def update_agent(self, profile: AgentProfile, old_profile: AgentProfile) -> AgentProfile:
        """更新已有 Agent 的配置：agent.yaml、SOUL.md、registry、引导文件。"""
        workspace_path = Path(profile.workspace_dir)

        cli_type_changed = profile.cli_config.cli_type != old_profile.cli_config.cli_type
        role_changed = profile.role_prompt != old_profile.role_prompt

        # 1. 更新 SOUL.md
        if role_changed:
            (workspace_path / "SOUL.md").write_text(profile.role_prompt, encoding="utf-8")

        # 2. 如果 CLI 类型变更，清理旧引导文件并写入新的
        if cli_type_changed:
            self._cleanup_old_instructions(workspace_path, old_profile.cli_config.cli_type)
            self._write_loading_instructions(workspace_path, profile.cli_config.cli_type)

        # 3. 保存 agent.yaml
        self._save_agent_yaml(profile)
        
        # 4. 注册
        self.registry.register_agent(profile)
        logger.info(f"Updated agent: {profile.agent_id}")
        return profile

    def _write_loading_instructions(self, workspace_path: Path, cli_type: str) -> None:
        """按 CLI 类型写入引导 Agent 加载 OpenClaw 文件的指令。"""
        if cli_type == "cursor":
            rules_dir = workspace_path / ".cursor" / "rules"
            rules_dir.mkdir(parents=True, exist_ok=True)
            content = (
                "---\n"
                "description: OpenClaw Persona & Memory Loader\n"
                "alwaysApply: true\n"
                "---\n\n"
                f"{OPENCLAW_LOADING_INSTRUCTION}"
            )
            (rules_dir / "role.mdc").write_text(content, encoding="utf-8")
        elif cli_type == "gemini":
            (workspace_path / "GEMINI.md").write_text(OPENCLAW_LOADING_INSTRUCTION, encoding="utf-8")
        else:
            (workspace_path / "CLAUDE.md").write_text(OPENCLAW_LOADING_INSTRUCTION, encoding="utf-8")

    def _cleanup_old_instructions(self, workspace_path: Path, old_cli_type: str) -> None:
        """清理旧的引导文件。"""
        if old_cli_type == "cursor":
            old_rule = workspace_path / ".cursor" / "rules" / "role.mdc"
            if old_rule.exists():
                old_rule.unlink()
        elif old_cli_type == "gemini":
            old_gemini = workspace_path / "GEMINI.md"
            if old_gemini.exists():
                old_gemini.unlink()
        else:
            old_claude = workspace_path / "CLAUDE.md"
            if old_claude.exists():
                old_claude.unlink()

    def _save_agent_yaml(self, profile: AgentProfile) -> None:
        """将 profile 序列化为 YAML 写入 workspace_dir/agent.yaml。"""
        workspace_path = Path(profile.workspace_dir)
        yaml_path = workspace_path / "agent.yaml"

        data = {
            "agent_id": profile.agent_id,
            "name": profile.name,
            "avatar": profile.avatar,
            "repo_url": profile.repo_url,
            "skills": profile.skills,
            "response_config": profile.response_config.model_dump(),
            "cli_config": profile.cli_config.model_dump(),
            "max_output_tokens": profile.max_output_tokens,
        }

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        logger.info(f"Saved agent config to workspace: {yaml_path}")

    def read_openclaw_file(self, agent_id: str, filename: str) -> str:
        """读取工作区下的特定 OpenClaw 文件（SOUL.md, AGENTS.md, USER.md）。"""
        profile = self.registry.get_agent(agent_id)
        file_path = Path(profile.workspace_dir) / filename
        if not file_path.exists():
            return ""
        return file_path.read_text(encoding="utf-8")

    def write_openclaw_file(self, agent_id: str, filename: str, content: str) -> None:
        """写入工作区下的特定 OpenClaw 文件。"""
        profile = self.registry.get_agent(agent_id)
        file_path = Path(profile.workspace_dir) / filename
        file_path.write_text(content, encoding="utf-8")
        if filename == "SOUL.md":
            profile.role_prompt = content
        logger.info(f"Wrote {filename} for {agent_id}")

    def read_workspace_config(self, agent_id: str) -> tuple[str, str]:
        """读取 SOUL.md 的内容（现在人设主要在这里）。"""
        profile = self.registry.get_agent(agent_id)
        soul_md = Path(profile.workspace_dir) / "SOUL.md"
        content = soul_md.read_text(encoding="utf-8") if soul_md.exists() else ""
        return content, "SOUL.md"

    def write_workspace_config(self, agent_id: str, content: str) -> None:
        """写入 SOUL.md。"""
        profile = self.registry.get_agent(agent_id)
        soul_md = Path(profile.workspace_dir) / "SOUL.md"
        soul_md.write_text(content, encoding="utf-8")
        profile.role_prompt = content
        logger.info(f"Wrote SOUL.md for {agent_id}")

    async def update_workspace(self, agent_id: str) -> None:
        """执行 git pull。"""
        profile = self.registry.get_agent(agent_id)
        workspace_path = Path(profile.workspace_dir)
        if not workspace_path.exists():
            raise FileNotFoundError(f"Workspace not found: {workspace_path}")

        if (workspace_path / ".git").exists():
            process = await asyncio.create_subprocess_exec(
                "git", "pull", cwd=str(workspace_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            logger.info(f"Updated workspace for {agent_id}")

    def list_workspaces(self) -> list[dict]:
        """返回工作区列表。"""
        result = []
        if not self.workspaces_dir.exists():
            return result
        for d in self.workspaces_dir.iterdir():
            if d.is_dir():
                result.append({
                    "agent_id": d.name,
                    "path": str(d),
                    "is_git_repo": (d / ".git").exists(),
                    "has_agent_yaml": (d / "agent.yaml").exists(),
                    "registered": d.name in self.registry.agents,
                })
        return result

    async def _clone_repo(self, repo_url: str, target_path: Path) -> None:
        """Git clone。"""
        if target_path.exists():
            return
        process = await asyncio.create_subprocess_exec(
            "git", "clone", repo_url, str(target_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
