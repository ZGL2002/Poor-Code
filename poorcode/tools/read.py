"""Read 工具——读取文件内容."""

from pathlib import Path

from poorcode.tools.base import Tool, ToolContext, ToolResult, truncate_result
from poorcode.tools.security import PathSecurityError, validate_path


class ReadTool(Tool):
    """读取指定文件的内容."""

    name = "read"
    category = "read"
    description = "读取文件内容。返回文件全文和总行数。用于查看代码、配置、文档等文本文件。"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要读取的文件路径，相对于当前工作目录",
            }
        },
        "required": ["file_path"],
    }

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """读取文件.

        Args:
            params: {"file_path": str}
            context: 执行上下文.

        Returns:
            ToolResult 含文件内容或错误信息.
        """
        file_path_str = params.get("file_path", "").strip()
        if not file_path_str:
            return ToolResult(
                success=False,
                error="invalid_params",
                content="缺少参数：file_path 不能为空",
            )

        # 路径校验
        try:
            target = validate_path(file_path_str, context.cwd)
        except PathSecurityError as e:
            return ToolResult(success=False, error="path_error", content=str(e))

        # 检查存在
        if not target.exists():
            return ToolResult(
                success=False,
                error="not_found",
                content=f"文件不存在：{file_path_str}",
            )

        if not target.is_file():
            return ToolResult(
                success=False,
                error="not_a_file",
                content=f"路径不是文件：{file_path_str}",
            )

        # 读取
        try:
            raw = target.read_text(encoding="utf-8")
        except PermissionError:
            return ToolResult(
                success=False,
                error="permission",
                content=f"没有读取权限：{file_path_str}",
            )
        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                error="binary",
                content=f"无法以文本方式读取（可能是二进制文件）：{file_path_str}",
            )

        lines = raw.splitlines()
        content = truncate_result(raw)

        result_text = (
            f"文件：{file_path_str}\n"
            f"行数：{len(lines)}\n"
            f"字符数：{len(raw)}\n"
            f"---\n"
            f"{content}"
        )
        return ToolResult(success=True, content=result_text)
