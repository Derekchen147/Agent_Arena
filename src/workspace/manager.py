"""工作区管理：Agent 接入、工作目录创建、角色配置写入、YAML 持久化与注册表同步。

接入流程：clone（或建空目录）→ 按 CLI 类型写角色配置 → 写 agents/{id}.yaml → registry.register
          → 初始化个人记忆目录（memory/）和 MEMORY.md 模板。

角色/System Prompt 约定：
- Claude CLI：工作目录下的 CLAUDE.md 作为该 Agent 的上下文与角色定义。
- Cursor CLI：工作目录下的 .cursor/rules/ 与 AGENTS.md 作为持久化规则（相当于 system prompt）；
  本模块会为 cursor 类型写入 .cursor/rules/role.mdc（alwaysApply），便于角色扮演与背景信息生效。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

import yaml

from src.memory.personal import PersonalMemoryManager
from src.models.agent import AgentProfile, CliConfig, ResponseConfig
from src.registry.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACES_DIR = "workspaces"
DEFAULT_AGENTS_DIR = "agents"


class WorkspaceManager:
    """负责 Agent 工作目录的创建、clone、CLAUDE.md 写入、YAML 持久化与 registry 注册/注销。"""

    def __init__(
        self,
        registry: AgentRegistry,
        workspaces_dir: str = DEFAULT_WORKSPACES_DIR,
        agents_config_dir: str = DEFAULT_AGENTS_DIR,
    ):
        """指定工作区根目录与 Agent 配置目录；工作区目录不存在时会创建。"""
        self.registry = registry
        self.workspaces_dir = Path(workspaces_dir)
        self.agents_config_dir = Path(agents_config_dir)
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
        """接入一个新的 AI 员工。

        完整流程：
        1. 如果有 repo_url，clone 到 workspaces/{agent_id}/
        2. 如果没有 repo_url，创建空的工作目录
        3. 写入 CLAUDE.md（角色上下文）
        4. 生成并保存 YAML 配置
        5. 注册到 AgentRegistry
        """
        workspace_path = self.workspaces_dir / agent_id

        # 有 repo_url 则 clone 到 workspaces/{agent_id}，否则创建空目录
        if repo_url:
            await self._clone_repo(repo_url, workspace_path)
        else:
            workspace_path.mkdir(parents=True, exist_ok=True)

        # 按 CLI 类型写入角色配置（若文件已存在则不覆盖，避免覆盖仓库自带配置）
        if role_prompt:
            if cli_type == "cursor":
                self._write_cursor_role_rule(workspace_path, role_prompt)
            else:
                self._write_claude_md(workspace_path, role_prompt)

        # 构造 AgentProfile，指向该工作目录与 CLI 类型
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

        # 将配置写入 agents/{agent_id}.yaml，便于重启后从磁盘加载
        self._save_agent_yaml(profile)

        # 写入内存中的注册表，供编排与 Worker 使用
        self.registry.register_agent(profile)

        # 初始化个人记忆目录和 MEMORY.md 模板
        self._personal_memory.init_workspace_memory(str(workspace_path), name)

        logger.info(f"Onboarded agent: {agent_id} ({name}) -> {workspace_path}")
        return profile

    async def remove_agent(self, agent_id: str, delete_workspace: bool = False) -> None:
        """从注册表注销、删除对应 YAML 文件，并可选的删除工作目录。"""
        self.registry.unregister_agent(agent_id)

        yaml_path = self.agents_config_dir / f"{agent_id}.yaml"
        if yaml_path.exists():
            yaml_path.unlink()

        if delete_workspace:
            workspace_path = self.workspaces_dir / agent_id
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
                logger.info(f"Deleted workspace: {workspace_path}")

        logger.info(f"Removed agent: {agent_id}")

    async def update_workspace(self, agent_id: str) -> None:
        """对该 Agent 的工作目录执行 git pull；非 git 目录则仅打日志不报错。"""
        profile = self.registry.get_agent(agent_id)
        workspace_path = Path(profile.workspace_dir)

        if not workspace_path.exists():
            raise FileNotFoundError(f"Workspace not found: {workspace_path}")

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
        """遍历 workspaces_dir 下每个子目录，返回路径、是否 git、是否有 CLAUDE.md、是否已注册。"""
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
        """将 repo_url clone 到 target_path；若目录已存在则执行 git pull。"""
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

    # ── 更新 Agent ──

    async def update_agent(self, profile: AgentProfile, old_profile: AgentProfile) -> AgentProfile:
        """更新已有 Agent 的配置：YAML、registry、workspace 角色文件。"""
        workspace_path = Path(profile.workspace_dir)

        cli_type_changed = profile.cli_config.cli_type != old_profile.cli_config.cli_type
        role_changed = profile.role_prompt != old_profile.role_prompt

        # cli_type 切换时，清理旧格式文件
        if cli_type_changed:
            if old_profile.cli_config.cli_type == "cursor":
                old_rule = workspace_path / ".cursor" / "rules" / "role.mdc"
                if old_rule.exists():
                    old_rule.unlink()
                    logger.info(f"Removed old .cursor/rules/role.mdc for {profile.agent_id}")
            else:
                old_claude = workspace_path / "CLAUDE.md"
                if old_claude.exists():
                    old_claude.unlink()
                    logger.info(f"Removed old CLAUDE.md for {profile.agent_id}")

        # role_prompt 或 cli_type 变更时，写入新格式角色文件
        if (role_changed or cli_type_changed) and profile.role_prompt:
            if profile.cli_config.cli_type == "cursor":
                self._force_write_cursor_role_rule(workspace_path, profile.role_prompt)
            else:
                self._force_write_claude_md(workspace_path, profile.role_prompt)

        self._save_agent_yaml(profile)
        self.registry.register_agent(profile)
        logger.info(f"Updated agent: {profile.agent_id}")
        return profile

    # ── Workspace 文件读写 ──

    def read_workspace_config(self, agent_id: str) -> tuple[str, str]:
        """读取 workspace 角色文件，返回 (content, filename)。"""
        profile = self.registry.get_agent(agent_id)
        workspace_path = Path(profile.workspace_dir)

        if profile.cli_config.cli_type == "cursor":
            filepath = workspace_path / ".cursor" / "rules" / "role.mdc"
            filename = ".cursor/rules/role.mdc"
        else:
            filepath = workspace_path / "CLAUDE.md"
            filename = "CLAUDE.md"

        content = filepath.read_text(encoding="utf-8") if filepath.exists() else ""
        return content, filename

    def write_workspace_config(self, agent_id: str, content: str) -> None:
        """直接写入 workspace 角色文件。"""
        profile = self.registry.get_agent(agent_id)
        workspace_path = Path(profile.workspace_dir)

        if profile.cli_config.cli_type == "cursor":
            rules_dir = workspace_path / ".cursor" / "rules"
            rules_dir.mkdir(parents=True, exist_ok=True)
            (rules_dir / "role.mdc").write_text(content, encoding="utf-8")
        else:
            (workspace_path / "CLAUDE.md").write_text(content, encoding="utf-8")

        logger.info(f"Wrote workspace config for {agent_id}")

    # ── 角色文件写入（onboard 用，不覆盖已有） ──

    def _write_claude_md(self, workspace_path: Path, role_prompt: str) -> None:
        """在工作目录下创建 CLAUDE.md 写入 role_prompt；若已存在则跳过避免覆盖仓库自带配置。"""
        claude_md = workspace_path / "CLAUDE.md"
        if claude_md.exists():
            logger.info(f"CLAUDE.md already exists in {workspace_path}, skipping write")
            return
        claude_md.write_text(role_prompt, encoding="utf-8")
        logger.info(f"Wrote CLAUDE.md to {workspace_path}")

    def _write_cursor_role_rule(self, workspace_path: Path, role_prompt: str) -> None:
        """为 Cursor CLI 在工作目录下写入 .cursor/rules/role.mdc，作为始终生效的角色/背景（system prompt）。

        Cursor 在 workspace_dir 下执行 agent 时会自动加载 .cursor/rules/*.mdc 与 AGENTS.md，
        alwaysApply: true 使该规则在每次对话中都被注入，从而实现明确的角色扮演与背景信息。
        """
        rules_dir = workspace_path / ".cursor" / "rules"
        rule_path = rules_dir / "role.mdc"
        if rule_path.exists():
            logger.info(f".cursor/rules/role.mdc already exists in {workspace_path}, skipping write")
            return
        rules_dir.mkdir(parents=True, exist_ok=True)
        content = (
            "---\n"
            "description: Agent role and background (always applied)\n"
            "alwaysApply: true\n"
            "---\n\n"
            f"{role_prompt}"
        )
        rule_path.write_text(content, encoding="utf-8")
        logger.info(f"Wrote .cursor/rules/role.mdc to {workspace_path}")

    # ── 角色文件强制写入（update 用，覆盖已有） ──

    def _force_write_claude_md(self, workspace_path: Path, role_prompt: str) -> None:
        """强制写入 CLAUDE.md（更新场景使用，覆盖已有文件）。"""
        claude_md = workspace_path / "CLAUDE.md"
        claude_md.write_text(role_prompt, encoding="utf-8")
        logger.info(f"Force wrote CLAUDE.md to {workspace_path}")

    def _force_write_cursor_role_rule(self, workspace_path: Path, role_prompt: str) -> None:
        """强制写入 .cursor/rules/role.mdc（更新场景使用，覆盖已有文件）。"""
        rules_dir = workspace_path / ".cursor" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        content = (
            "---\n"
            "description: Agent role and background (always applied)\n"
            "alwaysApply: true\n"
            "---\n\n"
            f"{role_prompt}"
        )
        (rules_dir / "role.mdc").write_text(content, encoding="utf-8")
        logger.info(f"Force wrote .cursor/rules/role.mdc to {workspace_path}")

    def _save_agent_yaml(self, profile: AgentProfile) -> None:
        """将 profile 序列化为 YAML 写入 agents_config_dir/{agent_id}.yaml。"""
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
