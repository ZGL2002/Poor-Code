"""TUI 应用管理——组合渲染与输入，管理 TUI 生命周期."""

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from poorcode.tui.input_area import PromptSession, create_input_session, get_input
from poorcode.tui.render import (
    render_agent_done,
    render_agent_progress,
    render_error,
    render_separator,
    render_status_bar,
    render_token_usage,
    render_tool_status,
    render_user_message,
    render_welcome,
)


class TuiApp:
    """TUI 应用类，管理终端界面的完整生命周期."""

    def __init__(
        self,
        provider_name: str,
        model_name: str,
        version: str,
        cwd: str,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self.version = version
        self.cwd = cwd

        self.console = Console()
        self._input_session: PromptSession = create_input_session()
        self._streaming = False
        self._live: Live | None = None
        self._stream_text = ""

    # ── 公开接口 ──────────────────────────────────────────

    def start(self) -> None:
        """显示欢迎界面和状态栏."""
        render_welcome(
            self.console,
            self.version,
            self.cwd,
            self.provider_name,
            self.model_name,
        )
        render_status_bar(self.console, self.provider_name, self.model_name)

    def show_user_message(self, text: str) -> None:
        """渲染用户消息."""
        render_user_message(self.console, text)

    def begin_streaming(self) -> None:
        """进入流式等待状态."""
        self._streaming = True
        self._stream_text = ""
        render_separator(self.console)

        # 用 Live 展示流式文本累积（transient 确保结束后自动清除）
        self._live = Live(
            Text("", style="white"),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()

    def stream_delta(self, delta: str) -> None:
        """追加流式文本增量."""
        if self._live is None:
            return
        self._stream_text += delta
        self._live.update(Text(self._stream_text, style="white"))

    def finish_streaming(self, full_text: str) -> None:
        """流式结束，用 Markdown 重新渲染."""
        if self._live is not None:
            self._live.stop()
            self._live = None

        self._streaming = False
        self._stream_text = ""

        if full_text.strip():
            try:
                md = Markdown(full_text, code_theme="monokai")
                self.console.print(md)
            except Exception:
                self.console.print(full_text)

        self.console.print()
        render_status_bar(self.console, self.provider_name, self.model_name)

    async def get_input(self) -> str:
        """获取用户输入."""
        return await get_input(self._input_session)

    def show_error(self, message: str) -> None:
        """显示错误信息."""
        self._streaming = False
        if self._live is not None:
            self._live.stop()
            self._live = None
        render_error(self.console, message)

    def show_tool_status(
        self,
        name: str,
        status: str,
        detail: str = "",
    ) -> None:
        """显示工具执行状态行.

        Args:
            name: 工具名.
            status: "running"、"done"、"error".
            detail: 失败时的错误码.
        """
        render_tool_status(self.console, name, status, detail)

    def show_agent_progress(self, iteration: int, max_iterations: int) -> None:
        """显示 Agent Loop 循环进度.

        Args:
            iteration: 当前轮次.
            max_iterations: 最大轮次.
        """
        render_agent_progress(self.console, iteration, max_iterations)

    def show_agent_done(
        self,
        reason: str,
        total_iterations: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """显示 Agent Loop 结束摘要.

        Args:
            reason: 停止原因.
            total_iterations: 总迭代轮次.
            input_tokens: 总输入 Token 数.
            output_tokens: 总输出 Token 数.
        """
        render_agent_done(
            self.console, reason, total_iterations, input_tokens, output_tokens
        )

    def show_token_usage(self, input_tokens: int, output_tokens: int) -> None:
        """显示 Token 用量.

        Args:
            input_tokens: 输入 Token 数.
            output_tokens: 输出 Token 数.
        """
        render_token_usage(self.console, input_tokens, output_tokens)

    @property
    def is_streaming(self) -> bool:
        """当前是否在流式接收中."""
        return self._streaming
