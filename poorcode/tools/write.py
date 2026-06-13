"""Write 工具——创建或覆盖文件."""

from poorcode.tools.base import Tool, ToolContext, ToolResult
from poorcode.tools.security import PathSecurityError, validate_path


class WriteTool(Tool):
    """创建或覆盖文件."""

    name = "write"
    category = "write"
    description = "创建或覆盖文件内容。父目录不存在时自动创建。用于新建文件或完全重写现有文件。"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径，相对于当前工作目录",
            },
            "content": {
                "type": "string",
                "description": "要写入文件的完整内容",
            },
        },
        "required": ["file_path", "content"],
    }

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """写入文件.

        Args:
            params: {"file_path": str, "content": str}
            context: 执行上下文.

        Returns:
            ToolResult.
        """
        file_path_str = params.get("file_path", "").strip()
        content = params.get("content", "")

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

        # 创建父目录
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return ToolResult(
                success=False,
                error="permission",
                content=f"没有权限创建目录：{target.parent}",
            )

        # 写入
        try:
            target.write_text(content, encoding="utf-8")
        except PermissionError:
            return ToolResult(
                success=False,
                error="permission",
                content=f"没有写入权限：{file_path_str}",
            )
        except OSError as e:
            return ToolResult(
                success=False,
                error="io_error",
                content=f"写入文件失败：{e}",
            )

        byte_count = len(content.encode("utf-8"))
        return ToolResult(
            success=True,
            content=(
                f"已写入：{file_path_str}\n"
                f"字符数：{len(content)}\n"
                f"字节数：{byte_count}"
            ),
        )
