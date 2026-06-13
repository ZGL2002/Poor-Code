"""Tool 抽象基类与核心数据结构."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

# 工具返回内容最大字节数（超此截断）
RESULT_MAX_SIZE = 100 * 1024  # 100 KB


@dataclass
class ToolResult:
    """工具执行结果，不论成功失败都返回此结构."""

    success: bool
    content: str  # 成功时的返回数据，或失败时的错误描述
    error: str | None = None  # 失败时的简短错误码，成功时为 None


@dataclass
class ToolContext:
    """工具执行时的上下文信息，由 Chat Loop 注入."""

    cwd: Path  # 当前工作目录
    timeout: float  # 本工具的执行超时秒数


class Tool(ABC):
    """工具抽象基类.

    每个工具需定义 name、description、parameters 三个元信息，
    并实现 async execute() 方法.
    """

    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)

    @abstractmethod
    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """执行工具.

        Args:
            params: 模型填入的参数，键值对.
            context: 执行上下文（工作目录、超时等）.

        Returns:
            ToolResult: 执行结果.
        """
        ...

    @property
    def default_timeout(self) -> float:
        """默认超时秒数，子类可覆盖."""
        return 30.0


def truncate_result(content: str, max_size: int = RESULT_MAX_SIZE) -> str:
    """截断过大的结果内容.

    Args:
        content: 原始内容.
        max_size: 最大字节数.

    Returns:
        截断后的内容（如被截断则附加提示）.
    """
    encoded = content.encode("utf-8")
    if len(encoded) <= max_size:
        return content
    # 截断到 max_size 字节，保留完整的 UTF-8 字符
    truncated = encoded[:max_size].decode("utf-8", errors="ignore")
    return truncated + "\n...(内容已截断，超过 100KB)"
