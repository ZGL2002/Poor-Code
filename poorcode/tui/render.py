"""TUI 渲染模块——用 Rich 库渲染所有终端输出."""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner

# ASCII 猫咪图案
CAT_ASCII = r"""
  /\_/\
 ( o.o )
  > ^ <
"""


def render_welcome(
    console: Console,
    version: str,
    cwd: str,
    provider_name: str,
    model_name: str,
) -> None:
    """渲染启动横幅."""
    console.print()
    console.print(CAT_ASCII, style="bold cyan")
    console.print(f"  PoorCode v{version}", style="bold white")
    console.print(f"  📁 {cwd}", style="dim")
    console.print()
    console.print("  输入消息开始对话，/quit 退出", style="dim italic")
    console.print()


def render_separator(console: Console) -> None:
    """渲染一条视觉分隔线."""
    console.print("─" * console.width, style="dim")


def render_user_message(console: Console, text: str) -> None:
    """渲染用户消息."""
    render_separator(console)
    panel = Panel(
        text.strip(),
        title="🧑 你",
        title_align="left",
        border_style="blue",
        padding=(0, 1),
    )
    console.print(panel)


def render_status_bar(
    console: Console,
    provider_name: str,
    model_name: str,
) -> None:
    """渲染底部状态栏.

    左侧：provider 名称，右侧：模型名称.
    """
    width = console.width
    left = f" 🔌 {provider_name} "
    right = f" 🧠 {model_name} "
    middle = width - len(left) - len(right)
    if middle < 1:
        middle = 1
    bar = left + " " * middle + right
    console.print(bar, style="reverse bold")


def render_tool_status(
    console: Console,
    tool_name: str,
    status: str,
    detail: str = "",
) -> None:
    """渲染工具执行状态行.

    Args:
        console: Rich Console.
        tool_name: 工具名（如 read、bash）.
        status: "running"、 "done"、 "error".
        detail: 失败时的错误码或简短说明.
    """
    if status == "running":
        icon = "⏳"
        text = f"🔧 {tool_name} … {icon} 执行中"
        style = "bold yellow"
    elif status == "done":
        icon = "✅"
        text = f"🔧 {tool_name} … {icon} 完成"
        style = "bold green"
    elif status == "error":
        icon = "❌"
        text = f"🔧 {tool_name} … {icon} {detail}".rstrip()
        style = "bold red"
    else:
        text = f"🔧 {tool_name} … {status}"
        style = "dim"

    console.print(text, style=style)


def render_error(console: Console, message: str) -> None:
    """以红色高亮显示错误信息."""
    console.print()
    console.print(f"  ❌ {message}", style="bold red")
    console.print()
