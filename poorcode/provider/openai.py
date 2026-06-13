"""OpenAI Chat Completions API Provider."""

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
from poorcode.tools.registry import to_openai_format


class OpenAIProvider(LLMProvider):
    """OpenAI Chat Completions API 协议实现.

    支持 SSE 流式响应和 tool calls.
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
            entry: dict = {"role": msg.role}
            # dict content → tool_calls 或直接透传
            if isinstance(msg.content, dict):
                if "tool_calls" in msg.content:
                    # assistant 消息含 tool_calls
                    entry["content"] = None
                    entry["tool_calls"] = msg.content["tool_calls"]
                else:
                    entry["content"] = str(msg.content)
            else:
                entry["content"] = msg.content
            # tool 角色需要 tool_call_id
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            result.append(entry)
        return result

    def _build_body(
        self,
        messages: list[dict],
    ) -> dict:
        body: dict = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
        }
        if self.tools:
            body["tools"] = to_openai_format(tools=self.tools)
        return body

    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        stream: bool = True,
    ) -> AsyncIterator[StreamEvent]:
        """流式对话（含 tool_calls 解析）."""
        url = self._build_url()
        headers = self._build_headers()
        api_messages = self._build_messages(messages, system_prompt)
        body = self._build_body(api_messages)

        # tool_calls 状态机：按 index 累积
        tool_calls_parts: dict[int, dict] = {}  # index → {id, name, arguments}
        has_text_content = False

        async for event in post_sse(url, headers, body):
            choices = event.get("choices", [])

            if not choices:
                continue

            choice = choices[0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")

            # 处理文本增量
            if "content" in delta and delta["content"] is not None:
                has_text_content = True
                yield StreamEvent(type="text_delta", content=delta["content"])

            # 处理 tool_calls 增量
            tool_calls_delta = delta.get("tool_calls")
            if tool_calls_delta:
                has_text_content = True  # 标记有内容产出来抑制 done
                for tc_delta in tool_calls_delta:
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls_parts:
                        tool_calls_parts[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    part = tool_calls_parts[idx]
                    if "id" in tc_delta and tc_delta["id"]:
                        part["id"] = tc_delta["id"]
                    if tc_delta.get("function"):
                        fn = tc_delta["function"]
                        if "name" in fn and fn["name"]:
                            part["name"] = fn["name"]
                        if "arguments" in fn:
                            part["arguments"] += fn["arguments"]

            # 流式结束或 tool_calls 完成
            if finish_reason:
                if finish_reason == "tool_calls" and tool_calls_parts:
                    # 检查多个工具调用
                    if len(tool_calls_parts) > 1:
                        # 只执行第一个，报错
                        first_key = sorted(tool_calls_parts.keys())[0]
                        first = tool_calls_parts[first_key]
                        try:
                            tool_input = json.loads(first["arguments"]) if first["arguments"].strip() else {}
                        except json.JSONDecodeError:
                            tool_input = {}
                        request = ToolCallRequest(
                            tool_name=first["name"],
                            tool_input=tool_input,
                            tool_use_id=first["id"],
                        )
                        yield StreamEvent(type="tool_call", content=json.dumps({
                            "tool_name": request.tool_name,
                            "tool_input": request.tool_input,
                            "tool_use_id": request.tool_use_id,
                        }))
                        yield StreamEvent(
                            type="tool_error",
                            content=(
                                f"模型请求了 {len(tool_calls_parts)} 个工具，"
                                f"本次仅支持 1 个。仅执行第 1 个。"
                            ),
                        )
                    else:
                        # 单个工具调用
                        for idx in sorted(tool_calls_parts.keys()):
                            part = tool_calls_parts[idx]
                            try:
                                tool_input = json.loads(part["arguments"]) if part["arguments"].strip() else {}
                            except json.JSONDecodeError:
                                yield StreamEvent(
                                    type="tool_error",
                                    content=(
                                        f"工具参数 JSON 解析失败："
                                        f"{part['arguments'][:200]}"
                                    ),
                                )
                                continue
                            request = ToolCallRequest(
                                tool_name=part["name"],
                                tool_input=tool_input,
                                tool_use_id=part["id"],
                            )
                            yield StreamEvent(type="tool_call", content=json.dumps({
                                "tool_name": request.tool_name,
                                "tool_input": request.tool_input,
                                "tool_use_id": request.tool_use_id,
                            }))

                    # tool_calls 完成后不 yield done（由 chat loop 二次调用后 yield）
                    return

                # 普通文本结束
                yield StreamEvent(type="done")
                return

    @staticmethod
    def build_tool_use_message(
        tool_call_id: str,
        tool_name: str,
        tool_input: dict,
    ) -> Message:
        """构建含工具调用的 assistant 消息.

        Args:
            tool_call_id: 工具调用 ID.
            tool_name: 工具名.
            tool_input: 模型填入的参数.

        Returns:
            可追加到对话历史的 assistant Message.
        """
        return Message(
            role="assistant",
            content={  # type: ignore[arg-type]
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_input, ensure_ascii=False),
                        },
                    }
                ]
            },
        )

    @staticmethod
    def build_tool_result_message(
        tool_call_id: str,
        tool_result: ToolResult,
    ) -> Message:
        """构建含工具执行结果的消息.

        Args:
            tool_call_id: 工具调用 ID.
            tool_result: 工具执行结果.

        Returns:
            可用于追加到对话历史的 Message（role=tool）.
        """
        content = tool_result.content
        if not tool_result.success and tool_result.error:
            content = f"[{tool_result.error}] {content}"

        return Message(role="tool", content=content, tool_call_id=tool_call_id)
