"""OpenAI Chat Completions API Provider."""

from collections.abc import AsyncIterator

from poorcode.provider.base import LLMProvider, Message, ProviderConfig, StreamEvent
from poorcode.provider.http import post_sse


class OpenAIProvider(LLMProvider):
    """OpenAI Chat Completions API 协议实现.

    支持 SSE 流式响应.
    """

    def _build_url(self) -> str:
        return f"{self.config.base_url}/v1/chat/completions"

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    def _build_messages(
        self, history: list[Message], system_prompt: str | None = None
    ) -> list[dict]:
        """将 Message 列表转为 OpenAI Chat Completions 格式."""
        result: list[dict] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        for msg in history:
            result.append({"role": msg.role, "content": msg.content})
        return result

    def _build_body(
        self,
        messages: list[dict],
    ) -> dict:
        return {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
        }

    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        stream: bool = True,
    ) -> AsyncIterator[StreamEvent]:
        """流式对话."""
        url = self._build_url()
        headers = self._build_headers()
        api_messages = self._build_messages(messages, system_prompt)
        body = self._build_body(api_messages)

        async for event in post_sse(url, headers, body):
            choices = event.get("choices", [])

            if not choices:
                continue

            choice = choices[0]
            delta = choice.get("delta", {})

            if "content" in delta and delta["content"] is not None:
                yield StreamEvent(type="text_delta", content=delta["content"])

            finish_reason = choice.get("finish_reason")
            if finish_reason:
                yield StreamEvent(type="done")
                return
