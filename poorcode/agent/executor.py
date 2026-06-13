"""工具执行器——按副作用分类，读类并发、写类串行."""

import asyncio
from pathlib import Path

from poorcode.agent.events import ToolResultEvent
from poorcode.provider.base import ToolCallRequest
from poorcode.tools.base import Tool, ToolContext, ToolResult


def classify(
    calls: list[ToolCallRequest],
    tools: dict[str, Tool],
) -> tuple[list[tuple[ToolCallRequest, Tool]], list[tuple[ToolCallRequest, Tool | None]]]:
    """按工具 category 分类.

    Args:
        calls: 工具调用请求列表.
        tools: 工具名 → 工具实例的映射.

    Returns:
        (read_calls, write_calls): 读类列表和写类列表，每项为 (call, tool) 配对.
            未注册的工具归入写类（保守处理）.
    """
    read_calls: list[tuple[ToolCallRequest, Tool]] = []
    write_calls: list[tuple[ToolCallRequest, Tool | None]] = []

    for call in calls:
        tool = tools.get(call.tool_name)
        if tool is not None and tool.category == "read":
            read_calls.append((call, tool))
        else:
            write_calls.append((call, tool))

    return read_calls, write_calls


async def execute_one(
    call: ToolCallRequest,
    tool: Tool | None,
    cwd: Path,
) -> tuple[ToolCallRequest, ToolResult]:
    """执行单个工具调用.

    Args:
        call: 工具调用请求.
        tool: 工具实例（None 表示未注册）.
        cwd: 工作目录.

    Returns:
        (call, result) 配对.
    """
    if tool is None:
        return (
            call,
            ToolResult(
                success=False,
                error="unknown_tool",
                content=f"工具 '{call.tool_name}' 未注册",
            ),
        )

    context = ToolContext(cwd=cwd, timeout=tool.default_timeout)
    try:
        result = await tool.execute(call.tool_input, context)
    except Exception as e:
        result = ToolResult(
            success=False,
            error="exception",
            content=f"工具执行异常：{e}",
        )
    return (call, result)


async def execute_all(
    calls: list[ToolCallRequest],
    tools: dict[str, Tool],
    cwd: Path,
) -> list[tuple[ToolCallRequest, ToolResult]]:
    """执行全部工具调用，按安全性分批，返回保持原始顺序的结果列表.

    读类（Read/Glob/Grep）→ 并发执行.
    写类（Write/Edit/Bash）→ 串行执行.
    混合时先并发跑完所有读类，再串行跑写类.

    Args:
        calls: 工具调用请求列表（保持 LLM 返回的原始顺序）.
        tools: 工具名 → 工具实例的映射.
        cwd: 工作目录.

    Returns:
        list[tuple[ToolCallRequest, ToolResult]]: 按原始顺序排列的 (调用, 结果) 配对.
    """
    if not calls:
        return []

    read_calls, write_calls = classify(calls, tools)

    # 用 dict 暂存，最后按原始顺序输出
    results_map: dict[str, tuple[ToolCallRequest, ToolResult]] = {}

    # 阶段一：读类并发
    if read_calls:
        read_tasks = [
            execute_one(call, tool, cwd) for call, tool in read_calls
        ]
        read_results = await asyncio.gather(*read_tasks)
        for call, result in read_results:
            results_map[call.tool_use_id] = (call, result)

    # 阶段二：写类串行
    for call, tool in write_calls:
        call_result, result = await execute_one(call, tool, cwd)
        results_map[call_result.tool_use_id] = (call_result, result)

    # 按原始顺序输出
    return [results_map[call.tool_use_id] for call in calls if call.tool_use_id in results_map]
