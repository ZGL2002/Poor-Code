"""工具系统——启动时自动注册全部六个工具."""

from poorcode.tools.base import Tool, ToolContext, ToolResult
from poorcode.tools.bash import BashTool
from poorcode.tools.edit import EditTool
from poorcode.tools.glob import GlobTool
from poorcode.tools.grep import GrepTool
from poorcode.tools.read import ReadTool
from poorcode.tools.registry import (
    get,
    list_tools,
    register,
    to_anthropic_format,
    to_openai_format,
)
from poorcode.tools.write import WriteTool

# 启动时自动注册全部六个核心工具
register(ReadTool())
register(WriteTool())
register(EditTool())
register(BashTool())
register(GlobTool())
register(GrepTool())

__all__ = [
    "Tool",
    "ToolResult",
    "ToolContext",
    "register",
    "get",
    "list_tools",
    "to_anthropic_format",
    "to_openai_format",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "BashTool",
    "GlobTool",
    "GrepTool",
]
