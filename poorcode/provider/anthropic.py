"""Anthropic Messages API Provider."""

import json
from collections.abc import AsyncIterator

from poorcode.provider.base import (
    LLMProvider,
    Message,
    ProviderConfig,
    StreamEvent,
    ToolCallRequest,
)
from poorcode.provider.http import post_sse
from poorcode.tools.base import ToolResult
from poorcode.tools.registry import to_anthropic_format


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API 协议实现.

    支持 SSE 流式响应、extended thinking、tool use.
    """

    def _build_url(self) -> str:
        return f"{self.config.base_url}/v1/messages"

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        return headers

    def _build_messages(self, history: list[Message]) -> list[dict]:
        """将 Message 列表转为 Anthropic Messages 格式.

        content 为字符串时转为纯文本；为 list 时直接透传（如 tool_result block）.
        """
        result = []
        for msg in history:
            if isinstance(msg.content, str):
                result.append({"role": msg.role, "content": msg.content})
            else:
                # content 已经是 Anthropic 格式的 content block list
                result.append({"role": msg.role, "content": msg.content})
        return result

    def _build_body(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
    ) -> dict:
        body: dict = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
            "max_tokens": 4096,
        }
        if system_prompt:
            body["system"] = system_prompt
        if self.tools:
            body["tools"] = to_anthropic_format(tools=self.tools)
        return body

    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        stream: bool = True,
    ) -> AsyncIterator[StreamEvent]:
        """流式对话（含 tool use 解析）."""
        url = self._build_url()
        headers = self._build_headers()
        api_messages = self._build_messages(messages)
        body = self._build_body(api_messages, system_prompt)

        # tool_use 状态机变量
        tool_use_count = 0
        current_tool_id: str | None = None
        current_tool_name: str | None = None
        current_tool_json: str = ""
        in_tool_use: bool = False

        async for event in post_sse(url, headers, body):
            event_type = event.get("type", "")

            if event_type == "content_block_start":
                content_block = event.get("content_block", {})
                block_type = content_block.get("type", "text")

                if block_type == "tool_use":
                    tool_use_count += 1
                    in_tool_use = True
                    current_tool_id = content_block.get("id", "")
                    current_tool_name = content_block.get("name", "")
                    current_tool_json = ""

                    # 超过 1 个工具调用时报错
                    if tool_use_count > 1:
                        yield StreamEvent(
                            type="tool_error",
                            content=(
                                f"模型请求了 {tool_use_count} 个工具"
                                f"（{current_tool_name} 等），"
                                f"本次仅支持 1 个。仅执行第 1 个。"
                            ),
                        )
                else:
                    in_tool_use = False
                continue

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                delta_type = delta.get("type", "")

                if delta_type == "text_delta":
                    yield StreamEvent(type="text_delta", content=delta.get("text", ""))

                elif delta_type == "thinking_delta":
                    yield StreamEvent(
                        type="thinking_delta", content=delta.get("thinking", "")
                    )

                elif delta_type == "input_json_delta":
                    # 累积 JSON 碎片
                    current_tool_json += delta.get("partial_json", "")

            elif event_type == "content_block_stop":
                if in_tool_use and current_tool_name and tool_use_count == 1:
                    # 尝试解析累积的 JSON
                    try:
                        tool_input = json.loads(current_tool_json) if current_tool_json.strip() else {}
                    except json.JSONDecodeError:
                        yield StreamEvent(
                            type="tool_error",
                            content=(
                                f"工具参数 JSON 解析失败："
                                f"{current_tool_json[:200]}"
                            ),
                        )
                        in_tool_use = False
                        continue

                    request = ToolCallRequest(
                        tool_name=current_tool_name,
                        tool_input=tool_input,
                        tool_use_id=current_tool_id or "",
                    )
                    yield StreamEvent(type="tool_call", content=json.dumps({
                        "tool_name": request.tool_name,
                        "tool_input": request.tool_input,
                        "tool_use_id": request.tool_use_id,
                    }))
                in_tool_use = False
                continue

            elif event_type == "message_stop":
                yield StreamEvent(type="done")
                return

            elif event_type == "message_start":
                continue

            elif event_type == "ping":
                continue

            elif event_type == "error":
                error_data = event.get("error", {})
                raise RuntimeError(
                    f"Anthropic API 错误：{error_data.get('message', str(event))}"
                )

    @staticmethod
    def build_tool_use_message(
        tool_use_id: str,
        tool_name: str,
        tool_input: dict,
    ) -> Message:
        """构建含工具调用的 assistant 消息.

        Args:
            tool_use_id: 工具调用 ID.
            tool_name: 工具名.
            tool_input: 模型填入的参数.

        Returns:
            可追加到对话历史的 assistant Message.
        """
        return Message(
            role="assistant",
            content=[  # type: ignore[arg-type]
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": tool_input,
                }
            ],
        )

    @staticmethod
    def format_tool_result(
        tool_use_id: str,
        tool_result: ToolResult,
    ) -> dict:
        """将工具执行结果转为 Anthropic tool_result content block.

        Args:
            tool_use_id: 工具调用 ID.
            tool_result: 工具执行结果.

        Returns:
            Anthropic 格式的 tool_result content block dict.
        """
        content = tool_result.content
        if not tool_result.success and tool_result.error:
            content = f"[{tool_result.error}] {content}"

        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
        }

    @staticmethod
    def build_tool_result_message(
        tool_use_id: str,
        tool_result: ToolResult,
    ) -> Message:
        """构建含工具执行结果的消息.

        Args:
            tool_use_id: 工具调用 ID.
            tool_result: 工具执行结果.

        Returns:
            可用于追加到对话历史的 Message.
        """
        result_block = AnthropicProvider.format_tool_result(
            tool_use_id, tool_result
        )
        return Message(
            role="user",
            content=[result_block],  # type: ignore[arg-type]
        )
