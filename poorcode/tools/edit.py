"""Edit 工具——精确字符串替换改文件."""

from poorcode.tools.base import Tool, ToolContext, ToolResult
from poorcode.tools.security import PathSecurityError, validate_path


class EditTool(Tool):
    """在文件中查找原文并精确替换一次.

    要求 old_string 在文件中精确唯一匹配：
    - 0 次匹配：返回 not_found 错误
    - >1 次匹配：返回 not_unique 错误并列出上下文
    - 1 次匹配：执行替换并写回
    """

    name = "edit"
    category = "write"
    description = (
        "修改文件内容：在文件中查找指定原文（old_string）并替换为新文（new_string）。"
        "要求原文精确唯一匹配——匹配到 0 处或 >1 处均报错且不修改文件。"
        "提供 old_string 时必须包含足够上下文使其唯一。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要修改的文件路径，相对于当前工作目录",
            },
            "old_string": {
                "type": "string",
                "description": "要替换的原文，必须在文件中精确唯一匹配",
            },
            "new_string": {
                "type": "string",
                "description": "替换后的新文",
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """执行替换.

        Args:
            params: {"file_path": str, "old_string": str, "new_string": str}
            context: 执行上下文.

        Returns:
            ToolResult.
        """
        file_path_str = params.get("file_path", "").strip()
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", "")

        if not file_path_str:
            return ToolResult(
                success=False,
                error="invalid_params",
                content="缺少参数：file_path 不能为空",
            )
        if not old_string:
            return ToolResult(
                success=False,
                error="invalid_params",
                content="缺少参数：old_string 不能为空",
            )

        # 路径校验
        try:
            target = validate_path(file_path_str, context.cwd)
        except PathSecurityError as e:
            return ToolResult(success=False, error="path_error", content=str(e))

        # 检查文件存在
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

        # 读取文件
        try:
            content = target.read_text(encoding="utf-8")
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
                content=f"无法以文本方式处理（可能是二进制文件）：{file_path_str}",
            )

        # 统计匹配次数
        count = content.count(old_string)
        if count == 0:
            return ToolResult(
                success=False,
                error="not_found",
                content=(
                    f"未找到原文。文件 {file_path_str} 中不存在指定的 old_string。\n"
                    f"请确认字符串内容与文件中完全一致（包括空白字符）。"
                ),
            )

        if count > 1:
            # 列出各匹配位置的上下文
            lines = content.splitlines()
            contexts = []
            for i, line in enumerate(lines, start=1):
                if old_string in line:
                    contexts.append(f"  第 {i} 行: {line.strip()[:120]}")
            return ToolResult(
                success=False,
                error="not_unique",
                content=(
                    f"原文不唯一：匹配到 {count} 处。"
                    f"请提供更多上下文使 old_string 唯一匹配。\n"
                    f"各匹配位置：\n" + "\n".join(contexts[:10])
                    + ("\n..." if len(contexts) > 10 else "")
                ),
            )

        # 唯一匹配，执行替换
        new_content = content.replace(old_string, new_string, 1)
        try:
            target.write_text(new_content, encoding="utf-8")
        except PermissionError:
            return ToolResult(
                success=False,
                error="permission",
                content=f"没有写入权限：{file_path_str}",
            )

        # 定位替换位置
        idx = content.index(old_string)
        line_num = content[:idx].count("\n") + 1

        return ToolResult(
            success=True,
            content=(
                f"已替换 1 处：{file_path_str}\n"
                f"位置：第 {line_num} 行附近\n"
                f"替换前：{old_string[:80]}{'...' if len(old_string) > 80 else ''}\n"
                f"替换后：{new_string[:80]}{'...' if len(new_string) > 80 else ''}"
            ),
        )
