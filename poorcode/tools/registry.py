"""工具注册中心——维护工具名到实例的映射，提供协议格式转换."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poorcode.tools.base import Tool

# 模块级注册表：工具名 → 工具实例
_registry: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """注册一个工具实例.

    Args:
        tool: Tool 实例，按 tool.name 注册.
    """
    _registry[tool.name] = tool


def get(name: str) -> Tool | None:
    """按名查找工具.

    Args:
        name: 工具名.

    Returns:
        Tool 实例或 None.
    """
    return _registry.get(name)


def list_tools() -> list[Tool]:
    """返回全部已注册工具.

    Returns:
        Tool 实例列表.
    """
    return list(_registry.values())


def to_anthropic_format(tools: list[Tool] | None = None) -> list[dict]:
    """将工具描述转为 Anthropic Messages API 格式.

    Args:
        tools: 工具列表，None 时使用全局注册表中的全部工具.

    Returns:
        Anthropic tools 数组，每项含 name、description、input_schema.
    """
    if tools is None:
        tools = list(_registry.values())
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


def to_openai_format(tools: list[Tool] | None = None) -> list[dict]:
    """将工具描述转为 OpenAI Chat Completions API 格式.

    Args:
        tools: 工具列表，None 时使用全局注册表中的全部工具.

    Returns:
        OpenAI tools 数组，每项含 type='function' 和嵌套的 function 对象.
    """
    if tools is None:
        tools = list(_registry.values())
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]
