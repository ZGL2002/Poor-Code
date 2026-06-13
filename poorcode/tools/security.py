"""路径安全校验——确保文件操作不越界."""

from pathlib import Path


class PathSecurityError(ValueError):
    """路径安全异常."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def validate_path(file_path: str, cwd: Path) -> Path:
    """校验文件路径是否在工作目录范围内.

    Args:
        file_path: 用户/模型提供的文件路径（相对路径）.
        cwd: 工作目录绝对路径.

    Returns:
        解析后的绝对路径.

    Raises:
        PathSecurityError: 路径为绝对路径或越界时.
    """
    path = Path(file_path)

    # 拒绝绝对路径
    if path.is_absolute():
        raise PathSecurityError(
            f"不允许绝对路径：{file_path}。请使用相对于工作目录的路径。"
        )

    # 解析为绝对路径
    cwd_resolved = cwd.resolve()
    resolved = (cwd_resolved / path).resolve()

    # 检查是否在工作目录内
    try:
        resolved.relative_to(cwd_resolved)
    except ValueError:
        raise PathSecurityError(
            f"路径越界：{file_path} 指向了工作目录之外的位置。"
            f"工作目录：{cwd_resolved}"
        ) from None

    return resolved
