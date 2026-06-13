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


def render_agent_progress(
    console: Console,
    iteration: int,
    max_iterations: int,
) -> None:
    """渲染 Agent Loop 循环进度.

    Args:
        console: Rich Console.
        iteration: 当前轮次（从 1 开始）.
        max_iterations: 最大轮次.
    """
    console.print(
        f"🔄 第 {iteration}/{max_iterations} 轮",
        style="bold cyan",
    )


def render_agent_done(
    console: Console,
    reason: str,
    total_iterations: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """渲染 Agent Loop 结束摘要.

    Args:
        console: Rich Console.
        reason: 停止原因.
        total_iterations: 总迭代轮次.
        input_tokens: 总输入 Token 数.
        output_tokens: 总输出 Token 数.
    """
    reason_labels = {
        "natural_stop": "✅ 完成",
        "max_iterations": "⏰ 达到迭代上限",
        "user_cancel": "🛑 用户取消",
        "consecutive_unknown_tools": "⚠️ 连续调用未注册工具",
        "stream_error": "❌ 流式错误",
    }
    label = reason_labels.get(reason, f"停止（{reason}）")

    parts = [f"{label}（{total_iterations} 轮"]
    if input_tokens or output_tokens:
        parts.append(f"，{input_tokens}+{output_tokens} tokens")
    parts.append("）")

    console.print("".join(parts), style="dim")


def render_token_usage(
    console: Console,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """渲染单次 LLM 调用的 Token 用量.

    Args:
        console: Rich Console.
        input_tokens: 输入 Token 数.
        output_tokens: 输出 Token 数.
    """
    console.print(
        f"📊 Token: {input_tokens} in + {output_tokens} out",
        style="dim",
    )
