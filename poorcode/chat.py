"""Chat Loop 编排层——用户输入循环 + Plan Mode + Agent Loop 驱动."""

import asyncio
import os
from enum import Enum
from pathlib import Path

from poorcode import __version__
from poorcode.agent import (
    AgentDoneEvent,
    AgentLoop,
    AgentProgressEvent,
    ErrorEvent,
    TextDeltaEvent,
    TokenUsageEvent,
)
from poorcode.agent.events import ToolResultEvent
from poorcode.config import load_config
from poorcode.provider import create_provider
from poorcode.provider.base import LLMProvider, Message
from poorcode.tools import list_tools
from poorcode.tools.base import Tool
from poorcode.tui import TuiApp


class AgentMode(Enum):
    """Agent 工作模式."""
    PLAN = "plan"  # 仅读类工具
    DO = "do"      # 全部工具


def _get_tools_for_mode(mode: AgentMode) -> list[Tool]:
    """根据模式筛选工具列表.

    Args:
        mode: PLAN 仅返回读类工具, DO 返回全部.

    Returns:
        筛选后的 Tool 列表.
    """
    all_tools = list_tools()
    if mode == AgentMode.PLAN:
        return [t for t in all_tools if t.category == "read"]
    return all_tools


def _handle_command(user_input: str) -> tuple[bool, str | None]:
    """解析用户命令.

    Args:
        user_input: 用户输入字符串.

    Returns:
        (is_command, response): is_command 表示是否为命令,
        response 是命令的响应消息（普通消息时为 None）。
    """
    stripped = user_input.strip().lower()
    if stripped in ("/quit", "/exit"):
        return True, None  # None 表示退出
    if stripped == "/plan":
        return True, "plan"
    if stripped == "/do":
        return True, "do"
    return False, None


async def run() -> int:
    """应用入口：加载配置、创建 Provider、启动对话循环.

    Returns:
        int: 退出码，0 表示正常退出.
    """
    # 1. 加载配置
    app_config = load_config()
    provider_config = app_config.provider

    # 2. 创建 Provider
    provider: LLMProvider = create_provider(provider_config)

    # 3. 初始化 TUI
    cwd = os.getcwd()
    tui = TuiApp(
        provider_name=provider_config.protocol,
        model_name=provider_config.model,
        version=__version__,
        cwd=cwd,
    )
    tui.start()

    # 4. Agent Loop 状态
    history: list[Message] = []
    mode: AgentMode = AgentMode.DO
    cancel_event = asyncio.Event()

    while True:
        # 获取用户输入
        try:
            user_input = await tui.get_input()
        except EOFError:
            break

        # 空输入跳过
        if not user_input.strip():
            continue

        # 命令处理
        is_cmd, cmd = _handle_command(user_input)
        if is_cmd:
            if cmd is None:
                # /quit, /exit
                tui.console.print("\n👋 再见！", style="bold")
                break
            elif cmd == "plan":
                mode = AgentMode.PLAN
                tui.console.print("📋 已切换到 Plan Mode（仅可调研代码）", style="bold cyan")
            elif cmd == "do":
                mode = AgentMode.DO
                tui.console.print("🔧 已切换到执行模式（可修改文件）", style="bold cyan")
            continue

        # 普通对话
        tui.show_user_message(user_input)
        history.append(Message(role="user", content=user_input))

        # 根据模式设置工具
        tools = _get_tools_for_mode(mode)
        provider.tools = tools

        # 创建 Agent Loop
        loop = AgentLoop(
            provider=provider,
            tools=tools,
            max_iterations=app_config.max_iterations,
            cancel_event=cancel_event,
        )

        # 消费 AgentEvent 流
        full_text = ""
        in_streaming = False
        agent_done: AgentDoneEvent | None = None
        cancel_event.clear()

        try:
            async for event in loop.run(history=history):
                if isinstance(event, AgentProgressEvent):
                    tui.show_agent_progress(
                        event.iteration, event.max_iterations
                    )

                elif isinstance(event, TextDeltaEvent):
                    if not in_streaming:
                        tui.begin_streaming()
                        in_streaming = True
                        full_text = ""
                    full_text += event.content
                    # 不逐个 push delta，等 done 后一次性渲染 Markdown
                    # （Rich Live 模式下文本已经实时显示了）

                elif isinstance(event, ToolResultEvent):
                    tui.show_tool_status(
                        event.tool_name,
                        "done" if event.success else "error",
                        event.error or "",
                    )

                elif isinstance(event, TokenUsageEvent):
                    tui.show_token_usage(
                        event.input_tokens, event.output_tokens
                    )

                elif isinstance(event, AgentDoneEvent):
                    agent_done = event
                    # 先结束流式
                    if in_streaming and full_text.strip():
                        tui.finish_streaming(full_text)
                        in_streaming = False
                    tui.show_agent_done(
                        event.reason,
                        event.total_iterations,
                        event.total_input_tokens,
                        event.total_output_tokens,
                    )

                elif isinstance(event, ErrorEvent):
                    tui.show_error(event.message)
                    if not event.recoverable:
                        break

        except KeyboardInterrupt:
            # 用户按 Ctrl+C 取消当前 Agent Loop
            cancel_event.set()
            tui.show_error("Agent Loop 已取消")
            # 恢复输入
            in_streaming = False

        if in_streaming and full_text.strip():
            tui.finish_streaming(full_text)

    return 0
