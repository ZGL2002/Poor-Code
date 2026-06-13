"""Anthropic Messages API Provider."""

from collections.abc import AsyncIterator

from poorcode.provider.base import LLMProvider, Message, ProviderConfig, StreamEvent
from poorcode.provider.http import post_sse


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API 协议实现.

    支持 SSE 流式响应和 extended thinking.
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
        """将 Message 列表转为 Anthropic Messages 格式."""
        return [
            {"role": msg.role, "content": msg.content}
            for msg in history
        ]

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
        return body

    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        stream: bool = True,
    ) -> AsyncIterator[StreamEvent]:
        """流式对话."""
        url = self._build_url()
        headers = self._build_headers()
        api_messages = self._build_messages(messages)
        body = self._build_body(api_messages, system_prompt)

        async for event in post_sse(url, headers, body):
            event_type = event.get("type", "")

            if event_type == "content_block_start":
                # 记录 content block 类型，用于后续 delta 判断
                content_block = event.get("content_block", {})
                block_type = content_block.get("type", "text")
                # 用内部变量追踪当前 block 类型
                # 简化处理：通过 delta 自身携带的信息判断
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
                    # tool use 相关，本次迭代暂不处理
                    pass

            elif event_type == "content_block_stop":
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
