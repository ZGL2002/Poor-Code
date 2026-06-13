"""Agent Loop 核心——ReAct 模式循环编排."""

import asyncio
import os
from pathlib import Path

from poorcode.agent.collector import StreamingCollector
from poorcode.agent.events import (
    AgentDoneEvent,
    AgentProgressEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolResultEvent,
)
from poorcode.agent.executor import execute_all
from poorcode.agent.stop import StopChecker
from poorcode.provider.base import LLMProvider, Message, ToolCallRequest
from poorcode.tools.base import Tool, ToolResult


class AgentLoop:
    """ReAct 模式 Agent Loop.

    循环调用 LLM → 收集响应 → 执行工具 → 回灌结果 → 继续，
    直到满足停止条件。通过 AsyncIterator[AgentEvent] 与外部通信.
    """

    def __init__(
        self,
        provider: LLMProvider,
        tools: list[Tool],
        max_iterations: int = 25,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._tools_map: dict[str, Tool] = {t.name: t for t in tools}
        self._max_iterations = max_iterations
        self._cancel_event = cancel_event
        self._cwd = Path(os.getcwd())

    async def run(
        self,
        history: list[Message],
        system_prompt: str | None = None,
    ):
        """执行 Agent Loop，产出 AgentEvent 流.

        Args:
            history: 对话历史（原地修改，工具消息和最终回复会追加）.
            system_prompt: 可选的系统提示.

        Yields:
            AgentEvent: 文本增量、工具调用、工具结果、进度、结束等事件.
        """
        stop_checker = StopChecker(self._max_iterations)
        iteration = 0
        total_input_tokens = 0
        total_output_tokens = 0

        while True:
            # 检查用户取消
            if self._cancel_event and self._cancel_event.is_set():
                yield AgentDoneEvent(
                    reason="user_cancel",
                    total_iterations=iteration,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )
                return

            iteration += 1
            yield AgentProgressEvent(
                iteration=iteration,
                max_iterations=self._max_iterations,
            )

            # 调用 LLM
            try:
                stream = self._provider.chat(
                    messages=history,
                    system_prompt=system_prompt,
                    stream=True,
                )
            except Exception as e:
                yield ErrorEvent(message=f"LLM 调用失败：{e}", recoverable=False)
                yield AgentDoneEvent(
                    reason="stream_error",
                    total_iterations=iteration,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )
                return

            # 流式收集
            collector = StreamingCollector()
            stream_error: str | None = None

            try:
                async for agent_event in collector.collect(stream):
                    # 跟踪错误
                    if isinstance(agent_event, ErrorEvent):
                        if not agent_event.recoverable:
                            stream_error = agent_event.message
                        else:
                            # 可恢复错误继续转发
                            yield agent_event
                    elif isinstance(agent_event, (TextDeltaEvent,)):
                        yield agent_event
                    else:
                        # ToolCallEvent、ThinkingDeltaEvent 等直接转发
                        yield agent_event
            except Exception as e:
                stream_error = f"流式接收异常：{e}"

            if stream_error:
                yield ErrorEvent(message=stream_error, recoverable=False)
                yield AgentDoneEvent(
                    reason="stream_error",
                    total_iterations=iteration,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )
                return

            # 检查停止条件（致命流错误已在上面 try/except 中处理，
            # collector 的 error_message 记录的是可恢复的 tool 解析警告，不在此终止）
            stop_reason = stop_checker.check(
                iteration=iteration,
                tool_calls=collector.tool_calls,
            )

            if stop_reason == "natural_stop":
                # 追加 assistant 消息
                if collector.full_text.strip():
                    history.append(
                        Message(role="assistant", content=collector.full_text)
                    )
                yield AgentDoneEvent(
                    reason="natural_stop",
                    total_iterations=iteration,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )
                return

            if stop_reason:
                yield AgentDoneEvent(
                    reason=stop_reason,
                    total_iterations=iteration,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )
                return

            # 有工具调用：执行
            if collector.tool_calls:
                # 跟踪连续未知工具
                for call in collector.tool_calls:
                    tool_exists = call.tool_name in self._tools_map
                    stop_checker.register_tool_result(tool_exists)

                unknown_reason = stop_checker.check_consecutive_unknown()
                if unknown_reason:
                    yield AgentDoneEvent(
                        reason=unknown_reason,
                        total_iterations=iteration,
                        total_input_tokens=total_input_tokens,
                        total_output_tokens=total_output_tokens,
                    )
                    return

                # 执行工具（读类并发，写类串行）
                results = await execute_all(
                    collector.tool_calls,
                    self._tools_map,
                    self._cwd,
                )

                # 产出结果事件
                for call, result in results:
                    yield _to_result_event(call, result)

                # 结果回灌历史
                self._append_tool_results(history, results)

                # 继续循环
                continue

            # 无工具调用且无文本（边缘情况）
            if collector.full_text.strip():
                history.append(
                    Message(role="assistant", content=collector.full_text)
                )
            yield AgentDoneEvent(
                reason="natural_stop",
                total_iterations=iteration,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
            )
            return

    def _append_tool_results(
        self,
        history: list[Message],
        results: list[tuple[ToolCallRequest, ToolResult]],
    ) -> None:
        """将工具调用和结果追加到对话历史.

        同一轮 LLM 响应的多个工具调用合并为一条 assistant 消息，
        多个工具结果合并为一条 user（Anthropic）或多条 tool（OpenAI）消息.
        """
        provider_type = type(self._provider).__name__

        if not results:
            return

        if provider_type == "AnthropicProvider":
            # 合并所有 tool_use 到一个 assistant content block 列表
            tool_use_blocks: list[dict] = []
            for call, _ in results:
                tool_use_blocks.append({
                    "type": "tool_use",
                    "id": call.tool_use_id,
                    "name": call.tool_name,
                    "input": call.tool_input,
                })
            history.append(Message(role="assistant", content=tool_use_blocks))

            # 合并所有 tool_result 到一个 user content block 列表
            tool_result_blocks: list[dict] = []
            for call, result in results:
                content = result.content
                if not result.success and result.error:
                    content = f"[{result.error}] {content}"
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": call.tool_use_id,
                    "content": content,
                })
            history.append(Message(role="user", content=tool_result_blocks))

        elif provider_type == "OpenAIProvider":
            import json

            # 合并所有 tool_calls 到一个 assistant 消息
            tool_calls_list: list[dict] = []
            for call, _ in results:
                tool_calls_list.append({
                    "id": call.tool_use_id,
                    "type": "function",
                    "function": {
                        "name": call.tool_name,
                        "arguments": json.dumps(call.tool_input, ensure_ascii=False),
                    },
                })
            history.append(Message(
                role="assistant",
                content={"tool_calls": tool_calls_list},
            ))

            # 每个 tool_result 单独一条 tool 消息
            for call, result in results:
                content = result.content
                if not result.success and result.error:
                    content = f"[{result.error}] {content}"
                history.append(Message(
                    role="tool",
                    content=content,
                    tool_call_id=call.tool_use_id,
                ))

        else:
            # 回退：纯文本追加
            for call, result in results:
                history.append(Message(
                    role="assistant",
                    content=f"[调用工具 {call.tool_name}]",
                ))
                history.append(Message(
                    role="user",
                    content=f"工具 {call.tool_name} 结果：{result.content}",
                ))


def _to_result_event(
    call: ToolCallRequest, result: ToolResult
) -> ToolResultEvent:
    """将执行结果转为事件."""
    preview = (
        result.content[:100] + "..."
        if len(result.content) > 100
        else result.content
    )
    return ToolResultEvent(
        tool_name=call.tool_name,
        tool_use_id=call.tool_use_id,
        success=result.success,
        error=result.error,
        content_preview=preview,
    )
