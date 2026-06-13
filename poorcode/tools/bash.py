"""Bash 工具——执行 Shell 命令."""

import asyncio
import os
import signal

from poorcode.tools.base import Tool, ToolContext, ToolResult, truncate_result


class BashTool(Tool):
    """在子进程中执行 Shell 命令."""

    name = "bash"
    category = "write"
    description = (
        "执行 Shell 命令并返回 stdout、stderr 和退出码。"
        "适合编译、测试、文件操作等需要命令行的任务。"
        "命令超时 120 秒，长时间操作请拆分步骤。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 Shell 命令",
            }
        },
        "required": ["command"],
    }

    @property
    def default_timeout(self) -> float:
        """覆盖默认超时为 120 秒."""
        return 120.0

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """执行命令.

        Args:
            params: {"command": str}
            context: 执行上下文.

        Returns:
            ToolResult.
        """
        command = params.get("command", "").strip()
        if not command:
            return ToolResult(
                success=False,
                error="invalid_params",
                content="缺少参数：command 不能为空",
            )

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(context.cwd),
                start_new_session=True,  # 将子进程放入独立进程组，便于超时时整组 kill
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=context.timeout
                )
            except asyncio.TimeoutError:
                # 杀死整个进程组（shell + 子进程）
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    process.kill()
                await process.wait()
                return ToolResult(
                    success=False,
                    error="timeout",
                    content=(
                        f"命令执行超时（{context.timeout} 秒）：{command}\n"
                        f"建议缩小操作范围或拆分步骤。"
                    ),
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            exit_code = process.returncode or 0

            result_parts = [f"退出码：{exit_code}"]
            if stdout:
                result_parts.append(f"stdout:\n{stdout.rstrip()}")
            if stderr:
                result_parts.append(f"stderr:\n{stderr.rstrip()}")

            full_output = "\n".join(result_parts)

            return ToolResult(
                success=exit_code == 0,
                content=truncate_result(full_output),
                error=None if exit_code == 0 else f"exit_code={exit_code}",
            )

        except OSError as e:
            return ToolResult(
                success=False,
                error="os_error",
                content=f"无法执行命令：{e}",
            )
