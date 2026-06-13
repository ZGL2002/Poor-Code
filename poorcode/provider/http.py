"""HTTP SSE 流式请求封装."""

import json
from collections.abc import AsyncIterator

import httpx

SSE_TIMEOUT = 60.0  # 连接超时（秒）


class SSEError(Exception):
    """SSE 传输层错误."""


async def post_sse(
    url: str,
    headers: dict[str, str],
    json_body: dict,
    timeout: float = SSE_TIMEOUT,
) -> AsyncIterator[dict]:
    """发送 POST 请求，逐行读取 SSE 事件流，yield 解析后的 JSON dict.

    Args:
        url: 请求地址.
        headers: HTTP 请求头.
        json_body: JSON 请求体.
        timeout: 连接/读取超时秒数.

    Yields:
        dict: 每个 SSE 事件的 data 字段 JSON 解析结果.

    Raises:
        SSEError: 网络错误、HTTP 错误、SSE 解析错误时抛出（含中文描述）.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=json_body,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise SSEError(
                        f"HTTP {response.status_code}：服务器返回错误\n{body.decode(errors='replace')[:500]}"
                    )

                current_event = None
                current_data: list[str] = []

                async for line in response.aiter_lines():
                    line = line.strip()

                    if not line:
                        # 空行表示事件结束
                        if current_data:
                            raw = "".join(current_data)
                            if raw.strip() == "[DONE]":
                                # OpenAI 流结束标记
                                current_event = None
                                current_data = []
                                continue
                            try:
                                yield json.loads(raw)
                            except json.JSONDecodeError as e:
                                raise SSEError(
                                    f"SSE 数据解析失败：{e}\n原始数据：{raw[:200]}"
                                ) from e
                        current_event = None
                        current_data = []
                        continue

                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                    elif line.startswith("data:"):
                        current_data.append(line[5:].strip())
                    # 忽略 comment 行（以 : 开头）和其他未知字段

    except httpx.TimeoutException:
        raise SSEError("请求超时，请检查网络或稍后重试") from None
    except httpx.NetworkError as e:
        raise SSEError(f"网络连接失败：{e}") from e
    except OSError as e:
        raise SSEError(f"连接异常：{e}") from e
