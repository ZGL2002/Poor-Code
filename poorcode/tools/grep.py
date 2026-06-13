"""Grep 工具——搜索代码内容."""

import re
from pathlib import Path

from poorcode.tools.base import Tool, ToolContext, ToolResult
from poorcode.tools.security import PathSecurityError, validate_path


class GrepTool(Tool):
    """在文件中搜索匹配正则表达式的行."""

    name = "grep"
    description = (
        "在代码中搜索匹配正则表达式的行。"
        "返回匹配行列表，含文件路径、行号、行内容。"
        "用于查找函数定义、导入、变量引用等。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "正则表达式搜索模式，如 'def test_*' 或 'import os'",
            },
            "path": {
                "type": "string",
                "description": "搜索目录，相对于工作目录。不指定则搜索整个工作目录。",
            },
            "glob": {
                "type": "string",
                "description": "文件名过滤 glob，如 '*.py' 只搜索 Python 文件。不指定则搜索所有文本文件。",
            },
        },
        "required": ["pattern"],
    }

    # 跳过这些目录
    SKIP_DIRS = {
        ".git",
        ".svn",
        ".hg",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        ".eggs",
        "dist",
        "build",
    }
    # 结果截断上限
    MAX_MATCHES = 500
    # 文件大小上限（跳过超大文件）
    MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """搜索内容.

        Args:
            params: {"pattern": str, "path"?: str, "glob"?: str}
            context: 执行上下文.

        Returns:
            ToolResult.
        """
        pattern_str = params.get("pattern", "").strip()
        search_path_str = params.get("path", "").strip()
        glob_pattern = params.get("glob", "").strip()

        if not pattern_str:
            return ToolResult(
                success=False,
                error="invalid_params",
                content="缺少参数：pattern 不能为空",
            )

        # 编译正则
        try:
            regex = re.compile(pattern_str)
        except re.error as e:
            return ToolResult(
                success=False,
                error="invalid_regex",
                content=f"正则表达式无效：{e}",
            )

        # 确定搜索目录
        if search_path_str:
            try:
                search_dir = validate_path(search_path_str, context.cwd)
            except PathSecurityError as e:
                return ToolResult(success=False, error="path_error", content=str(e))
            if not search_dir.exists():
                return ToolResult(
                    success=False,
                    error="not_found",
                    content=f"目录不存在：{search_path_str}",
                )
            if not search_dir.is_dir():
                return ToolResult(
                    success=False,
                    error="not_a_dir",
                    content=f"路径不是目录：{search_path_str}",
                )
        else:
            search_dir = context.cwd.resolve()

        # 收集文件列表
        if glob_pattern:
            files = list(search_dir.rglob(glob_pattern))
        else:
            files = [p for p in search_dir.rglob("*") if p.is_file()]

        # 搜索结果
        results: list[dict] = []
        for fpath in files:
            # 跳过隐藏目录和构建目录
            parts = set(fpath.parts)
            if parts & self.SKIP_DIRS:
                continue

            # 跳过超大文件和二进制
            try:
                if fpath.stat().st_size > self.MAX_FILE_SIZE:
                    continue
            except OSError:
                continue

            try:
                rel = fpath.relative_to(context.cwd.resolve())
            except ValueError:
                rel = fpath

            try:
                lines = fpath.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

            for line_num, line in enumerate(lines, start=1):
                if regex.search(line):
                    results.append(
                        {
                            "file": str(rel),
                            "line_num": line_num,
                            "text": line.rstrip(),
                        }
                    )
                    if len(results) >= self.MAX_MATCHES:
                        break

            if len(results) >= self.MAX_MATCHES:
                break

        # 格式化输出
        if not results:
            return ToolResult(
                success=True,
                content=f"未找到匹配 '{pattern_str}' 的行。",
            )

        lines_out = []
        for r in results:
            lines_out.append(f"{r['file']}:{r['line_num']}: {r['text'][:200]}")

        output = "\n".join(lines_out)

        if len(results) >= self.MAX_MATCHES:
            output += f"\n...(已截断，超过 {self.MAX_MATCHES} 条匹配)"

        return ToolResult(
            success=True,
            content=f"搜索 '{pattern_str}'，找到 {len(results)} 条匹配：\n{output}",
        )
