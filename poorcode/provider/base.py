"""Provider 抽象层：核心数据结构与接口定义."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class Message:
    """标准化的对话消息，与协议无关."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class StreamEvent:
    """流式响应中的统一事件结构."""

    type: str  # "text_delta", "thinking_delta", "done"
    content: str = ""


@dataclass
class ProviderConfig:
    """从 YAML 解析出的 Provider 配置."""

    protocol: str  # "anthropic" 或 "openai"
    model: str
    base_url: str
    api_key: str


class LLMProvider(ABC):
    """LLM Provider 抽象基类。新增后端只需继承并实现 chat()."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

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
            StreamEvent: 流式事件（text_delta / thinking_delta / done）.
        """
        ...
