"""流式收集器——消费 Provider 的 StreamEvent，实时转发文本，同时累积完整响应."""

import json
from collections.abc import AsyncIterator

from poorcode.agent.events import (
    AgentEvent,
    ErrorEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallEvent,
)
from poorcode.provider.base import StreamEvent, ToolCallRequest


class StreamingCollector:
    """消费 Provider 的 AsyncIterator[StreamEvent]，转为 AgentEvent 流.

    双路设计：
    - 实时路：text_delta / thinking_delta 立即以 AgentEvent 转发
    - 累积路：完整文本和工具调用列表在流结束后供 Agent Loop 判断
    """

    def __init__(self) -> None:
        self._full_text: str = ""
        self._tool_calls: list[ToolCallRequest] = []
        self._had_error: bool = False
        self._error_message: str = ""

    async def collect(
        self, stream: AsyncIterator[StreamEvent]
    ) -> AsyncIterator[AgentEvent]:
        """消费 StreamEvent 流，产出 AgentEvent 流.

        Args:
            stream: Provider.chat() 产出的 StreamEvent 迭代器.

        Yields:
            AgentEvent: 文本增量、思考增量、工具调用、错误等事件.
        """
        self._full_text = ""
        self._tool_calls = []
        self._had_error = False
        self._error_message = ""

        async for event in stream:
            if event.type == "text_delta":
                self._full_text += event.content
                yield TextDeltaEvent(content=event.content)

            elif event.type == "thinking_delta":
                yield ThinkingDeltaEvent(content=event.content)

            elif event.type == "tool_call":
                # 解析 ToolCallRequest JSON
                try:
                    data = json.loads(event.content)
                    request = ToolCallRequest(
                        tool_name=data["tool_name"],
                        tool_input=data["tool_input"],
                        tool_use_id=data["tool_use_id"],
                    )
                    self._tool_calls.append(request)
                    yield ToolCallEvent(
                        tool_name=request.tool_name,
                        tool_input=request.tool_input,
                        tool_use_id=request.tool_use_id,
                    )
                except (json.JSONDecodeError, KeyError) as e:
                    self._had_error = True
                    self._error_message = f"工具调用解析失败：{e}"
                    yield ErrorEvent(
                        message=self._error_message,
                        recoverable=True,
                    )

            elif event.type == "tool_error":
                self._had_error = True
                self._error_message = event.content
                yield ErrorEvent(
                    message=event.content,
                    recoverable=True,
                )

            elif event.type == "done":
                # 流式结束，退出循环
                break

    @property
    def full_text(self) -> str:
        """累积的完整文本响应."""
        return self._full_text

    @property
    def tool_calls(self) -> list[ToolCallRequest]:
        """本轮 LLM 响应中的所有工具调用（按接收顺序）."""
        return self._tool_calls

    @property
    def had_error(self) -> bool:
        """流式期间是否发生过错误."""
        return self._had_error

    @property
    def error_message(self) -> str:
        """流式错误描述."""
        return self._error_message
