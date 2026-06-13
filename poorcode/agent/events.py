"""AgentEvent 类型定义——Agent Loop 与 TUI 之间的解耦事件流."""

from dataclasses import dataclass


@dataclass
class TextDeltaEvent:
    """流式文本增量."""
    content: str


@dataclass
class ThinkingDeltaEvent:
    """思考增量（extended thinking）."""
    content: str


@dataclass
class ToolCallEvent:
    """单个工具调用请求已就绪."""
    tool_name: str
    tool_input: dict
    tool_use_id: str


@dataclass
class ToolResultEvent:
    """工具执行完成."""
    tool_name: str
    tool_use_id: str
    success: bool
    error: str | None
    content_preview: str  # 结果摘要（不超过 100 字符）


@dataclass
class TokenUsageEvent:
    """单次 LLM 调用的 Token 用量."""
    input_tokens: int
    output_tokens: int


@dataclass
class AgentProgressEvent:
    """Agent Loop 循环进度."""
    iteration: int
    max_iterations: int


@dataclass
class AgentDoneEvent:
    """Agent Loop 结束信号.

    reason 取值:
        "natural_stop"              — 模型自然结束，不再请求工具
        "max_iterations"            — 达到迭代上限
        "user_cancel"               — 用户按 Esc 取消
        "consecutive_unknown_tools" — 连续 3 次调用未注册工具
        "stream_error"              — LLM 流式响应错误
    """
    reason: str
    total_iterations: int
    total_input_tokens: int = 0
    total_output_tokens: int = 0


@dataclass
class ErrorEvent:
    """错误事件."""
    message: str
    recoverable: bool = True


# 联合类型（运行时通过 isinstance 判断）
AgentEvent = (
    TextDeltaEvent
    | ThinkingDeltaEvent
    | ToolCallEvent
    | ToolResultEvent
    | TokenUsageEvent
    | AgentProgressEvent
    | AgentDoneEvent
    | ErrorEvent
)
