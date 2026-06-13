"""Chat Loop 编排——应用主循环."""

import os

from poorcode import __version__
from poorcode.config import load_config
from poorcode.provider import create_provider
from poorcode.provider.base import LLMProvider, Message, StreamEvent
from poorcode.tui import TuiApp


async def run() -> int:
    """应用入口：加载配置、创建 Provider、启动对话循环.

    Returns:
        int: 退出码，0 表示正常退出.
    """
    # 1. 加载配置
    config = load_config()

    # 2. 创建 Provider
    provider: LLMProvider = create_provider(config)

    # 3. 初始化 TUI
    cwd = os.getcwd()
    tui = TuiApp(
        provider_name=config.protocol,
        model_name=config.model,
        version=__version__,
        cwd=cwd,
    )
    tui.start()

    # 4. 对话循环
    history: list[Message] = []

    while True:
        try:
            user_input = await tui.get_input()
        except EOFError:
            break

        # 空输入跳过
        if not user_input.strip():
            continue

        # 退出命令
        if user_input.strip().lower() in ("/quit", "/exit"):
            tui.console.print("\n👋 再见！", style="bold")
            break

        # 追加用户消息（prompt_toolkit 回显已展示输入，不再重复渲染）
        history.append(Message(role="user", content=user_input))

        # 调用 Provider 流式对话
        tui.begin_streaming()
        full_response = ""

        try:
            async for event in provider.chat(messages=history, stream=True):
                if event.type == "text_delta":
                    full_response += event.content
                    tui.stream_delta(event.content)

                elif event.type == "thinking_delta":
                    # 缓存但不展示（内部推理）
                    pass

                elif event.type == "done":
                    tui.finish_streaming(full_response)
                    break

            # 追加助手消息到历史
            if full_response.strip():
                history.append(Message(role="assistant", content=full_response))

        except Exception as e:
            tui.show_error(f"{e}")
            # 不崩溃，继续下一轮

    return 0
