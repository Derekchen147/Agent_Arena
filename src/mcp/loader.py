"""MCP 配置加载器：从 Agent workspace 的 mcp/ 目录加载 MCP 服务器配置。

配置文件：{workspace_dir}/mcp/mcp_config.yaml

MCP 服务器分三类：
- bundled：脚本在 workspace 内，完全可迁移
- external：声明依赖外部包，需目标环境提供 credentials
- infrastructure：基础设施类，需目标环境适配

加载后生成 Claude CLI 格式的 JSON 配置文件供 --mcp-config 使用。
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class McpServerConfig:
    """单个 MCP 服务器的配置。"""
    server_id: str
    server_type: str = "external"      # bundled / external / infrastructure
    transport: str = "stdio"           # stdio / sse
    command: str = ""                  # 启动命令
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    required_env: list[str] = field(default_factory=list)  # 迁移时需配置的环境变量
    capability: str = ""               # infrastructure 类型的能力描述


@dataclass
class McpConfig:
    """一个 Agent 的完整 MCP 配置。"""
    servers: list[McpServerConfig] = field(default_factory=list)
    source_path: str = ""


def load_mcp_config(workspace_dir: str | Path) -> McpConfig | None:
    """从 workspace 的 mcp/mcp_config.yaml 加载 MCP 配置。"""
    config_path = Path(workspace_dir) / "mcp" / "mcp_config.yaml"
    if not config_path.exists():
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.warning("Failed to load MCP config from %s: %s", config_path, e)
        return None

    if not data or not isinstance(data, dict):
        return None

    servers: list[McpServerConfig] = []
    for srv_data in data.get("mcp_servers", []):
        srv = McpServerConfig(
            server_id=srv_data.get("id", ""),
            server_type=srv_data.get("type", "external"),
            transport=srv_data.get("transport", "stdio"),
            command=srv_data.get("command", ""),
            args=srv_data.get("args", []),
            env=srv_data.get("env", {}),
            required_env=srv_data.get("required_env", []),
            capability=srv_data.get("capability", ""),
        )
        servers.append(srv)

    config = McpConfig(servers=servers, source_path=str(config_path))
    logger.info(
        "Loaded MCP config from %s: %d servers (%s)",
        config_path, len(servers),
        ", ".join(s.server_id for s in servers),
    )
    return config


def resolve_mcp_command(server: McpServerConfig, workspace_dir: str | Path) -> McpServerConfig:
    """解析 bundled 类型的相对路径为绝对路径。"""
    if server.server_type == "bundled":
        workspace = Path(workspace_dir)
        # args 中的相对路径解析为 workspace 内的绝对路径
        resolved_args = []
        for arg in server.args:
            candidate = workspace / arg
            if candidate.exists():
                resolved_args.append(str(candidate))
            else:
                resolved_args.append(arg)
        server.args = resolved_args
    return server


def generate_claude_mcp_json(
    mcp_config: McpConfig,
    workspace_dir: str | Path,
    extra_env: dict[str, str] | None = None,
) -> str | None:
    """生成 Claude CLI 格式的 MCP 配置 JSON 文件，返回文件路径。

    Claude CLI 的 --mcp-config 接受 JSON 文件，格式：
    {
        "mcpServers": {
            "server_name": {
                "command": "...",
                "args": [...],
                "env": {...}
            }
        }
    }
    """
    if not mcp_config or not mcp_config.servers:
        return None

    mcp_servers = {}
    workspace = Path(workspace_dir)

    for srv in mcp_config.servers:
        srv = resolve_mcp_command(srv, workspace_dir)

        # 合并环境变量：server 自身 env + extra_env 中匹配 required_env 的
        env = dict(srv.env)
        if extra_env:
            for key in srv.required_env:
                if key in extra_env:
                    env[key] = extra_env[key]
            # 也合并所有 extra_env（adapter 层的 env）
            for key, val in extra_env.items():
                if key not in env:
                    env[key] = val

        server_entry: dict = {
            "command": srv.command,
            "args": srv.args,
        }
        if env:
            server_entry["env"] = env

        mcp_servers[srv.server_id] = server_entry

    if not mcp_servers:
        return None

    config_json = {"mcpServers": mcp_servers}

    # 写入 workspace 内的临时配置文件（固定位置，避免每次调用创建新文件）
    mcp_dir = workspace / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    config_file = mcp_dir / ".mcp_runtime.json"
    config_file.write_text(json.dumps(config_json, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("Generated MCP config JSON: %s (%d servers)", config_file, len(mcp_servers))
    return str(config_file)


def check_mcp_readiness(mcp_config: McpConfig, env: dict[str, str] | None = None) -> list[dict]:
    """检查 MCP 配置的就绪状态，返回每个 server 的状态。

    用于迁移检查：bundled 应可直接用，external 检查 required_env。
    """
    env = env or {}
    results = []
    for srv in mcp_config.servers:
        status: dict = {
            "server_id": srv.server_id,
            "type": srv.server_type,
            "ready": True,
            "missing_env": [],
        }
        if srv.required_env:
            missing = [k for k in srv.required_env if k not in env]
            if missing:
                status["ready"] = False
                status["missing_env"] = missing
        results.append(status)
    return results
