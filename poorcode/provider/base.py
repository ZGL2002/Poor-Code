"""Provider 抽象层：核心数据结构与接口定义."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poorcode.tools.base import Tool


@dataclass
class Message:
    """标准化的对话消息，与协议无关."""

    role: str  # "system", "user", "assistant", "tool"
    content: str | list | dict  # 文本内容，或 Anthropic content block list，或 OpenAI tool_calls dict
    tool_call_id: str | None = None  # OpenAI tool 角色消息的 tool_call_id


@dataclass
class StreamEvent:
    """流式响应中的统一事件结构.

    type 取值:
        "text_delta"     — 文本增量
        "thinking_delta" — 思考增量（extended thinking）
        "tool_call"      — 工具调用参数接收完毕
        "tool_error"     — 工具调用解析失败（多工具等）
        "done"           — 流式结束
    """

    type: str
    content: str = ""


@dataclass
class ToolCallRequest:
    """Provider 解析完流式 tool_use 事件后产出的统一结构."""

    tool_name: str  # 要调用的工具名
    tool_input: dict  # 模型填入的参数，键值对
    tool_use_id: str  # 协议层的调用 ID


@dataclass
class ProviderConfig:
    """从 YAML 解析出的 Provider 配置."""

    protocol: str  # "anthropic" 或 "openai"
    model: str
    base_url: str
    api_key: str


class LLMProvider(ABC):
    """LLM Provider 抽象基类。新增后端只需继承并实现 chat()."""

    def __init__(
        self,
        config: ProviderConfig,
        tools: list[Tool] | None = None,
    ) -> None:
        self.config = config
        self.tools: list[Tool] | None = tools

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        stream: bool = True,
    ) -> AsyncIterator[StreamEvent]:
        """发送消息，返回流式事件迭代器.

        Args:
            messages: 历史对话消息列表.
            system_prompt: 可选的系统提示.
            stream: 是否流式返回（本次迭代仅用 True）.

        Yields:
            StreamEvent: 流式事件（text_delta / thinking_delta / tool_call / tool_error / done）.
        """
        ...
