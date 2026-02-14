"""BaseAdapter：所有 CLI Adapter 的抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from src.models.protocol import AgentInput, AgentOutput


class BaseAdapter(ABC):
    """所有 CLI Adapter 的基类。

    每个 Adapter 负责：
    1. 在 Agent 的 workspace_dir 中启动 CLI 进程
    2. 把 AgentInput 转为 CLI 的输入
    3. 把 CLI 的输出解析为 AgentOutput
    """

    @abstractmethod
    async def invoke(
        self,
        input: AgentInput,
        workspace_dir: str,
        stream_callback: Callable[[str], None] | None = None,
    ) -> AgentOutput:
        """在指定工作目录中调用 CLI，返回结果。"""
        ...

    @abstractmethod
    async def health_check(self, workspace_dir: str) -> bool:
        """检查底层 CLI 是否可用。"""
        ...
