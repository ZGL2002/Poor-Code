"""TUI 输入模块——prompt_toolkit 输入框."""

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

INPUT_PLACEHOLDER = "Send a message... (Alt+Enter 换行, Enter 发送)"


def create_input_session() -> PromptSession:
    """创建配置好的 PromptSession.

    Enter 提交，Alt+Enter（Escape,Enter）插入换行.
    """
    kb = KeyBindings()

    @kb.add("enter")
    def handle_enter(event):
        buffer = event.current_buffer
        buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def handle_alt_enter(event):
        event.current_buffer.insert_text("\n")

    session: PromptSession = PromptSession(
        [("class:prompt", "❯ "), ("", " ")],
        multiline=True,
        key_bindings=kb,
        bottom_toolbar=INPUT_PLACEHOLDER,
    )
    return session


async def get_input(session: PromptSession) -> str:
    """异步获取用户输入.

    返回用户输入的文本。Ctrl+C 或 EOF 时返回 "/quit".
    """
    try:
        return await session.prompt_async()
    except KeyboardInterrupt:
        return "/quit"
    except EOFError:
        return "/quit"
