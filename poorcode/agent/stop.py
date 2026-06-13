"""停止条件检查器——统一的 Agent Loop 退出判断."""


class StopChecker:
    """评估 Agent Loop 状态，判断是否应停止.

    支持的停止条件（按优先级）:
        1. stream_error — LLM 流式错误
        2. max_iterations — 超过迭代上限
        3. natural_stop — 模型不再请求工具
        4. consecutive_unknown_tools — 连续 3 次调用未注册工具（需外部调用 check_consecutive_unknown）
    """

    def __init__(self, max_iterations: int) -> None:
        self.max_iterations = max_iterations
        self._consecutive_unknown: int = 0

    def check(
        self,
        iteration: int,
        tool_calls: list,
        stream_error: str | None = None,
    ) -> str | None:
        """检查是否应停止循环.

        Args:
            iteration: 当前迭代轮次（从 1 开始）.
            tool_calls: 本轮 LLM 响应中的工具调用列表.
            stream_error: LLM 流式错误描述（None 表示无错误）.

        Returns:
            停止原因字符串，或 None（继续循环）.
        """
        if stream_error:
            return "stream_error"
        if iteration > self.max_iterations:
            return "max_iterations"
        if not tool_calls:
            return "natural_stop"
        return None

    def register_tool_result(self, tool_exists: bool) -> None:
        """注册一个工具执行结果，用于跟踪连续未知工具.

        Args:
            tool_exists: 工具是否在注册表中存在.
        """
        if not tool_exists:
            self._consecutive_unknown += 1
        else:
            self._consecutive_unknown = 0

    def check_consecutive_unknown(self) -> str | None:
        """检查连续未知工具是否达到阈值.

        Returns:
            "consecutive_unknown_tools" 或 None.
        """
        if self._consecutive_unknown >= 3:
            return "consecutive_unknown_tools"
        return None

    def reset(self) -> None:
        """重置内部状态（如连续未知工具计数）."""
        self._consecutive_unknown = 0
