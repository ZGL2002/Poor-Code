"""Glob 工具——按模式匹配找文件."""

from pathlib import Path

from poorcode.tools.base import Tool, ToolContext, ToolResult, truncate_result
from poorcode.tools.security import PathSecurityError, validate_path


class GlobTool(Tool):
    """按 glob 模式匹配文件路径."""

    name = "glob"
    description = (
        "按 glob 模式查找匹配的文件路径。支持 ** 递归匹配。"
        "适合查找特定类型或命名模式的文件，如 '**/*.py' 找所有 Python 文件。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob 模式，如 '**/*.py' 或 'src/**/*.ts'。支持 ** 递归匹配。",
            }
        },
        "required": ["pattern"],
    }

    # 结果截断上限
    MAX_RESULTS = 200

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """查找文件.

        Args:
            params: {"pattern": str}
            context: 执行上下文.

        Returns:
            ToolResult.
        """
        pattern = params.get("pattern", "").strip()
        if not pattern:
            return ToolResult(
                success=False,
                error="invalid_params",
                content="缺少参数：pattern 不能为空",
            )

        # 确保基准目录可访问（不校验 pattern 内容本身）
        try:
            validate_path(".", context.cwd)
        except PathSecurityError as e:
            return ToolResult(success=False, error="path_error", content=str(e))

        cwd = context.cwd.resolve()
        matches = []
        try:
            for p in cwd.glob(pattern):
                if p.is_file():
                    try:
                        rel = p.relative_to(cwd)
                        matches.append(str(rel))
                    except ValueError:
                        # 符号链接指到外面导致 relative_to 失败，跳过
                        pass
        except OSError as e:
            return ToolResult(
                success=False,
                error="io_error",
                content=f"查找文件时出错：{e}",
            )

        if not matches:
            return ToolResult(success=True, content="未找到匹配的文件。")

        # 排序并截断
        matches.sort()
        truncated = matches[: self.MAX_RESULTS]
        content = "\n".join(truncated)

        if len(matches) > self.MAX_RESULTS:
            content += f"\n...(已截断，共 {len(matches)} 个结果，仅展示前 {self.MAX_RESULTS} 个)"

        return ToolResult(
            success=True,
            content=f"匹配 {len(matches)} 个文件：\n{content}",
        )
