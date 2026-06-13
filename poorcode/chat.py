"""Chat Loop 编排——应用主循环，含工具调用检测与执行."""

import json
import os
from pathlib import Path

from poorcode import __version__
from poorcode.config import load_config
from poorcode.provider import create_provider
from poorcode.provider.base import (
    LLMProvider,
    Message,
    ProviderConfig,
    StreamEvent,
    ToolCallRequest,
)
from poorcode.tui import TuiApp

# 导入工具系统（触发自动注册）
from poorcode.tools import get as get_tool
from poorcode.tools import list_tools
from poorcode.tools.base import ToolContext, ToolResult


def _build_tool_context(cwd: Path, timeout: float) -> ToolContext:
    """构造工具执行上下文."""
    return ToolContext(cwd=cwd, timeout=timeout)


async def _handle_tool_call(
    request: ToolCallRequest,
    provider: LLMProvider,
    history: list[Message],
    tui: TuiApp,
    cwd: Path,
) -> None:
    """执行工具调用并将结果回灌对话历史.

    Args:
        request: 工具调用请求.
        provider: LLM Provider 实例.
        history: 对话历史（原地修改）.
        tui: TUI 实例.
        cwd: 工作目录.
    """
    tool_name = request.tool_name
    tool_input = request.tool_input
    tool_use_id = request.tool_use_id

    # 查找工具
    tool = get_tool(tool_name)
    if tool is None:
        tui.show_tool_status(tool_name, "error", "工具未注册")
        # 构建错误结果
        error_result = ToolResult(
            success=False,
            error="unknown_tool",
            content=f"工具 '{tool_name}' 未注册。可用工具：{[t.name for t in list_tools()]}",
        )
        _append_tool_messages(provider, history, tool_use_id, tool_name, tool_input, error_result)
        return

    # 执行工具
    tui.show_tool_status(tool_name, "running")
    context = _build_tool_context(cwd, tool.default_timeout)

    try:
        result = await tool.execute(tool_input, context)
    except Exception as e:
        result = ToolResult(
            success=False,
            error="exception",
            content=f"工具执行异常：{e}",
        )

    # 显示结果状态
    if result.success:
        tui.show_tool_status(tool_name, "done")
    else:
        tui.show_tool_status(tool_name, "error", result.error or "")

    # 将工具调用和结果追加到历史
    _append_tool_messages(provider, history, tool_use_id, tool_name, tool_input, result)


def _append_tool_messages(
    provider: LLMProvider,
    history: list[Message],
    tool_use_id: str,
    tool_name: str,
    tool_input: dict,
    result: ToolResult,
) -> None:
    """将工具调用消息和工具结果消息追加到对话历史.

    不同协议构造不同的消息格式.
    """
    # 获取 provider 的具体类型以调用正确的静态方法
    provider_type = type(provider).__name__

    if provider_type == "AnthropicProvider":
        from poorcode.provider.anthropic import AnthropicProvider

        # 追加 assistant 消息（含 tool_use block）
        history.append(
            AnthropicProvider.build_tool_use_message(
                tool_use_id, tool_name, tool_input
            )
        )
        # 追加 user 消息（含 tool_result block）
        history.append(
            AnthropicProvider.build_tool_result_message(
                tool_use_id, result
            )
        )
    elif provider_type == "OpenAIProvider":
        from poorcode.provider.openai import OpenAIProvider

        # 追加 assistant 消息（含 tool_calls）
        history.append(
            OpenAIProvider.build_tool_use_message(
                tool_use_id, tool_name, tool_input
            )
        )
        # 追加 tool 消息（含 tool_call_id）
        history.append(
            OpenAIProvider.build_tool_result_message(
                tool_use_id, result
            )
        )
    else:
        # 回退：纯文本追加
        history.append(
            Message(role="assistant", content=f"[调用工具 {tool_name}]")
        )
        history.append(
            Message(
                role="user",
                content=f"工具 {tool_name} 结果：{result.content}",
            )
        )


async def run() -> int:
    """应用入口：加载配置、创建 Provider、启动对话循环.

    Returns:
        int: 退出码，0 表示正常退出.
    """
    # 1. 加载配置
    config = load_config()

    # 2. 创建 Provider（传入全部已注册工具）
    provider: LLMProvider = create_provider(config)
    provider.tools = list_tools()

    # 3. 初始化 TUI
    cwd = os.getcwd()
    tui = TuiApp(
        provider_name=config.protocol,
        model_name=config.model,
        version=__version__,
        cwd=cwd,
    )
    tui.start()

    # 4. 对话循环
    history: list[Message] = []

    while True:
        try:
            user_input = await tui.get_input()
        except EOFError:
            break

        # 空输入跳过
        if not user_input.strip():
            continue

        # 退出命令
        if user_input.strip().lower() in ("/quit", "/exit"):
            tui.console.print("\n👋 再见！", style="bold")
            break

        # 追加用户消息
        history.append(Message(role="user", content=user_input))

        # 调用 Provider 流式对话
        tui.begin_streaming()
        full_response = ""

        try:
            async for event in provider.chat(messages=history, stream=True):
                if event.type == "text_delta":
                    full_response += event.content
                    tui.stream_delta(event.content)

                elif event.type == "thinking_delta":
                    # 缓存但不展示
                    pass

                elif event.type == "tool_error":
                    # 工具调用解析失败
                    tui.show_error(event.content)

                elif event.type == "tool_call":
                    # 收到完整的工具调用请求
                    try:
                        request_data = json.loads(event.content)
                        request = ToolCallRequest(
                            tool_name=request_data["tool_name"],
                            tool_input=request_data["tool_input"],
                            tool_use_id=request_data["tool_use_id"],
                        )
                    except (json.JSONDecodeError, KeyError) as e:
                        tui.show_error(f"工具调用解析失败：{e}")
                        # 让流式结束
                        tui.finish_streaming("")
                        break

                    # 停止流式显示
                    tui.finish_streaming("")

                    # 执行工具并将结果注入历史
                    await _handle_tool_call(
                        request, provider, history, tui, Path(cwd)
                    )

                    # 第二次调用 Provider：获取模型对工具结果的文本回复
                    tui.begin_streaming()
                    full_response = ""
                    try:
                        async for event2 in provider.chat(
                            messages=history, stream=True
                        ):
                            if event2.type == "text_delta":
                                full_response += event2.content
                                tui.stream_delta(event2.content)

                            elif event2.type == "thinking_delta":
                                pass

                            elif event2.type == "tool_call":
                                # 模型尝试再次调用工具——本次不支持，忽略
                                tui.show_error(
                                    "模型尝试再次调用工具，当前版本不支持自动循环。"
                                )

                            elif event2.type == "tool_error":
                                tui.show_error(event2.content)

                            elif event2.type == "done":
                                tui.finish_streaming(full_response)
                                break
                    except Exception as e:
                        tui.show_error(f"{e}")

                    # 无论第二次调用成功与否，本轮结束（不继续循环工具调用）
                    if full_response.strip():
                        history.append(
                            Message(role="assistant", content=full_response)
                        )
                    break  # 跳出外层 for 循环

                elif event.type == "done":
                    tui.finish_streaming(full_response)
                    break

            # 追加助手消息到历史（纯文本回复的情况）
            if full_response.strip() and not _had_tool_call(history, full_response):
                history.append(Message(role="assistant", content=full_response))

        except Exception as e:
            tui.show_error(f"{e}")
            # 不崩溃，继续下一轮

    return 0


def _had_tool_call(history: list[Message], last_response: str) -> bool:
    """检查本轮对话是否已经通过工具调用的第二次 chat 追加过 assistant 消息.

    简单判断：如果 history 最后一条是 assistant 且内容非纯文本，说明已追加.
    """
    if not history:
        return False
    last = history[-1]
    if last.role != "assistant":
        return False
    # 如果最后一条 assistant 消息的内容不是纯字符串，则是工具调用追加的
    return not isinstance(last.content, str)
