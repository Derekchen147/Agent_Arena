"""技能加载器：从 Agent workspace 的 skills/ 目录加载 SKILL.md 文件。

每个技能是一个目录，内含 SKILL.md 文件（YAML frontmatter + Markdown body），
遵循 superpowers 格式：
    skills/
        code-review/
            SKILL.md
        systematic-debugging/
            SKILL.md

SKILL.md 格式：
    ---
    name: code-review
    description: 当需要审查代码质量时使用此技能
    ---
    # Code Review
    ## Overview
    ...（技能的完整指令）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SkillDefinition:
    """单个技能的定义。"""
    skill_id: str           # 目录名，如 "code-review"
    name: str               # frontmatter 中的 name
    description: str        # frontmatter 中的 description（仅描述何时使用）
    body: str               # Markdown 正文（完整技能指令）
    source_path: str = ""   # SKILL.md 的完整路径


def load_skills_from_workspace(workspace_dir: str | Path) -> list[SkillDefinition]:
    """从 workspace 的 skills/ 目录加载所有技能。

    扫描 {workspace_dir}/skills/ 下每个子目录的 SKILL.md 文件。
    返回解析后的 SkillDefinition 列表。
    """
    skills_dir = Path(workspace_dir) / "skills"
    if not skills_dir.exists():
        return []

    skills: list[SkillDefinition] = []
    for subdir in sorted(skills_dir.iterdir()):
        if not subdir.is_dir():
            continue
        skill_md = subdir / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            skill = _parse_skill_md(skill_md, subdir.name)
            skills.append(skill)
            logger.debug("Loaded skill: %s from %s", skill.name, skill_md)
        except Exception as e:
            logger.warning("Failed to load skill from %s: %s", skill_md, e)

    if skills:
        logger.info(
            "Loaded %d skills from %s: %s",
            len(skills), skills_dir,
            ", ".join(s.skill_id for s in skills),
        )
    return skills


def _parse_skill_md(path: Path, dir_name: str) -> SkillDefinition:
    """解析 SKILL.md：提取 YAML frontmatter 和 Markdown body。"""
    content = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)

    name = frontmatter.get("name", dir_name)
    description = frontmatter.get("description", "")

    return SkillDefinition(
        skill_id=dir_name,
        name=name,
        description=description,
        body=body.strip(),
        source_path=str(path),
    )


def _split_frontmatter(content: str) -> tuple[dict, str]:
    """将 '---\\n...yaml...\\n---\\n...body...' 拆为 (dict, body_str)。"""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        return {}, content

    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}

    return fm, match.group(2)


def build_skills_prompt_section(skills: list[SkillDefinition]) -> str:
    """将技能列表构建为注入 prompt 的文本段落。

    仅注入技能概览（name + description），不注入完整 body。
    完整 body 由 CLI 自身通过工作目录的 SKILL.md 文件加载。
    """
    if not skills:
        return ""

    lines = ["## 你的可用技能\n"]
    lines.append("以下是你已掌握的技能，在相关场景下应主动运用：\n")
    for skill in skills:
        lines.append(f"- **{skill.name}**: {skill.description}")
        lines.append(f"  （详见 skills/{skill.skill_id}/SKILL.md）")
    lines.append("")
    return "\n".join(lines)
