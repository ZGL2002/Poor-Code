# Agent Loop Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `poorcode/tools/base.py` | Tool 基类新增 `category` 属性 |
| 修改 | `poorcode/tools/read.py` | category = "read" |
| 修改 | `poorcode/tools/glob.py` | category = "read" |
| 修改 | `poorcode/tools/grep.py` | category = "read" |
| 修改 | `poorcode/tools/write.py` | category = "write" |
| 修改 | `poorcode/tools/edit.py` | category = "write" |
| 修改 | `poorcode/tools/bash.py` | category = "write" |
| 新建 | `poorcode/agent/__init__.py` | 导出 AgentLoop、AgentEvent、ToolExecutor |
| 新建 | `poorcode/agent/events.py` | AgentEvent 类型定义 |
| 新建 | `poorcode/agent/collector.py` | StreamingCollector |
| 新建 | `poorcode/agent/executor.py` | ToolExecutor（分类 + 并发/串行） |
| 新建 | `poorcode/agent/stop.py` | StopChecker |
| 新建 | `poorcode/agent/loop.py` | AgentLoop 主循环 |
| 修改 | `poorcode/config.py` | 新增 `max_iterations` 配置项 |
| 修改 | `config.yaml` | 新增 `max_iterations: 25` |
| 修改 | `poorcode/tui/app.py` | 新增消费 AgentEvent 的方法 |
| 修改 | `poorcode/tui/render.py` | 新增 progress 和 done 渲染 |
| 修改 | `poorcode/chat.py` | 重写为薄编排层 + Plan Mode |

## T1: Tool 基类增加 category 属性

**文件：** `poorcode/tools/base.py`、`poorcode/tools/read.py`、`poorcode/tools/glob.py`、`poorcode/tools/grep.py`、`poorcode/tools/write.py`、`poorcode/tools/edit.py`、`poorcode/tools/bash.py`

**依赖：** 无

**步骤：**
1. 在 `poorcode/tools/base.py` 的 `Tool` 基类中添加类属性 `category: str = "read"`
2. 在 `ReadTool`、`GlobTool`、`GrepTool` 中确认或添加 `category = "read"`
3. 在 `WriteTool`、`EditTool`、`BashTool` 中添加 `category = "write"`

**验证：** `python -c "from poorcode.tools import list_tools; print({t.name: t.category for t in list_tools()})"` 输出 `{'read': 'read', 'write': 'write', 'edit': 'write', 'bash': 'write', 'glob': 'read', 'grep': 'read'}`

## T2: AgentEvent 类型定义

**文件：** `poorcode/agent/events.py`（新建）

**依赖：** 无

**步骤：**
1. 定义 `TextDeltaEvent` dataclass —— 字段 `content: str`
2. 定义 `ThinkingDeltaEvent` dataclass —— 字段 `content: str`
3. 定义 `ToolCallEvent` dataclass —— 字段 `tool_name: str`、`tool_input: dict`、`tool_use_id: str`
4. 定义 `ToolResultEvent` dataclass —— 字段 `tool_name: str`、`tool_use_id: str`、`success: bool`、`error: str | None`、`content_preview: str`
5. 定义 `TokenUsageEvent` dataclass —— 字段 `input_tokens: int`、`output_tokens: int`
6. 定义 `AgentProgressEvent` dataclass —— 字段 `iteration: int`、`max_iterations: int`
7. 定义 `AgentDoneEvent` dataclass —— 字段 `reason: str`、`total_iterations: int`、`total_input_tokens: int`、`total_output_tokens: int`
8. 定义 `ErrorEvent` dataclass —— 字段 `message: str`、`recoverable: bool`
9. 定义联合类型 `AgentEvent = TextDeltaEvent | ThinkingDeltaEvent | ToolCallEvent | ToolResultEvent | TokenUsageEvent | AgentProgressEvent | AgentDoneEvent | ErrorEvent`

**验证：** `python -c "from poorcode.agent.events import AgentProgressEvent, AgentDoneEvent; e = AgentProgressEvent(iteration=1, max_iterations=25); print(e.iteration)"` 无报错，输出 `1`

## T3: 流式收集器

**文件：** `poorcode/agent/collector.py`（新建）

**依赖：** T2、`poorcode.provider.base.StreamEvent`、`poorcode.provider.base.ToolCallRequest`

**步骤：**
1. 实现 `StreamingCollector` 类
2. 构造函数初始化：`_full_text = ""`、`_tool_calls: list[ToolCallRequest] = []`、`_tool_use_count = 0`
3. 实现 `async collect(stream: AsyncIterator[StreamEvent]) -> AsyncIterator[AgentEvent]`：
   - 遍历 `stream` 中的每个 `StreamEvent`
   - `text_delta` → 拼接 `_full_text`，同步 `yield TextDeltaEvent(content=...)`
   - `thinking_delta` → `yield ThinkingDeltaEvent(content=...)`
   - `tool_call` → 解析 JSON 得到 `ToolCallRequest`，追加到 `_tool_calls`，`yield ToolCallEvent(...)`
   - `tool_error` → `yield ErrorEvent(message=..., recoverable=True)`
   - `done` → 直接结束循环（不 yield）
4. 暴露只读属性 `full_text: str` 和 `tool_calls: list[ToolCallRequest]`

**验证：** `python -c "from poorcode.agent.collector import StreamingCollector; c = StreamingCollector(); print(c.full_text, c.tool_calls)"` 无报错，输出空字符串和空列表

## T4: 停止条件检查器

**文件：** `poorcode/agent/stop.py`（新建）

**依赖：** 无

**步骤：**
1. 实现 `StopChecker` 类
2. 构造函数接收 `max_iterations: int`，初始化 `_consecutive_unknown: int = 0`
3. 实现 `check(iteration: int, tool_calls: list, stream_error: str | None = None) -> str | None`：
   - 若 `stream_error` → 返回 `"stream_error"`
   - 若 `iteration > max_iterations` → 返回 `"max_iterations"`
   - 若 `tool_calls` 为空（模型不再要工具）→ 返回 `"natural_stop"`（正常停止信号）
   - 否则返回 `None`（继续循环）
4. 实现 `register_tool_result(tool_name: str, tool_exists: bool)`：
   - 若 `not tool_exists`：`_consecutive_unknown += 1`
   - 若 `tool_exists`：`_consecutive_unknown = 0`
5. 实现 `check_consecutive_unknown() -> str | None`：
   - 若 `_consecutive_unknown >= 3` → 返回 `"consecutive_unknown_tools"`
   - 否则返回 `None`
6. 实现 `reset()` → 重置 `_consecutive_unknown = 0`

**验证：** 临时脚本：创建 StopChecker(25)，iteration=3, tool_calls 非空 → check() 返回 None；iteration=26 → 返回 "max_iterations"

## T5: 工具执行器

**文件：** `poorcode/agent/executor.py`（新建）

**依赖：** T1、T2、`poorcode.tools.base`、`poorcode.provider.base.ToolCallRequest`

**步骤：**
1. 实现 `classify(calls: list[ToolCallRequest], tools: dict[str, Tool]) -> tuple[list, list]`：
   - 遍历 calls，查 tools 获取 tool 实例
   - `tool.category == "read"` → 放入读类列表
   - 否则 → 放入写类列表
   - 工具未注册 → 放入写类列表（保守处理，含错误结果）
2. 实现 `async execute_all(calls: list[ToolCallRequest], tools: dict[str, Tool], cwd: Path) -> AsyncIterator[AgentEvent]`：
   - 调用 `classify()` 分类
   - 读类并发：`await asyncio.gather(*[execute_one(call, tools, cwd) for call in read_calls])`
   - 写类串行：`for call in write_calls: await execute_one(call, tools, cwd)`
   - 每完成一个工具就 `yield ToolResultEvent(...)`
   - 返回结果保持原始 `calls` 顺序
3. 实现 `async execute_one(call, tools, cwd) -> tuple[ToolCallRequest, ToolResult]`：
   - 查工具，构造 `ToolContext(cwd=Path(cwd), timeout=...)`
   - 执行，捕获异常
   - 返回 `(call, result)` 配对

**验证：** `python -c "from poorcode.agent.executor import ToolExecutor; e = ToolExecutor(); print('ok')"` 无报错

## T6: Agent Loop 主循环

**文件：** `poorcode/agent/loop.py`（新建）

**依赖：** T2、T3、T4、T5、Provider、工具注册表

**步骤：**
1. 实现 `AgentLoop` 类
2. 构造函数接收：
   - `provider: LLMProvider`
   - `tools: list[Tool]`（当前模式下的工具列表）
   - `max_iterations: int = 25`
   - `cancel_flag: asyncio.Event | None = None`（Esc 取消）
3. 实现 `async run(history: list[Message], system_prompt: str | None = None) -> AsyncIterator[AgentEvent]`：
   - 初始化 `StopChecker(max_iterations)`、`iteration = 0`、`total_input_tokens = 0`、`total_output_tokens = 0`
   - **循环**：
     - `iteration += 1`
     - yield `AgentProgressEvent(iteration, max_iterations)`
     - 检查 `cancel_flag.is_set()` → yield `AgentDoneEvent(reason="user_cancel", ...)` → 退出
     - 调用 `provider.chat(messages=history, stream=True)` 获取 SSE 流
     - 创建 `StreamingCollector`，`async for event in collector.collect(stream): yield event`
     - 若 collector 产出过 `ErrorEvent` 且不可恢复 → yield `AgentDoneEvent(reason="stream_error", ...)` → 退出
     - 从 provider 响应中提取 token 用量（如有），yield `TokenUsageEvent(...)`
     - 调用 `stop_checker.check(iteration, collector.tool_calls)`
       - 返回 `"natural_stop"` → yield `AgentDoneEvent(reason="natural_stop", ...)` → 退出
       - 返回 `"max_iterations"` → yield `AgentDoneEvent(reason="max_iterations", ...)` → 退出
       - 返回其他原因 → yield `AgentDoneEvent(reason=..., ...)` → 退出
     - 若 collector 有 tool_calls：
       - `async for event in ToolExecutor.execute_all(collector.tool_calls, self._tools_map, cwd): yield event`
       - 检查连续未知工具（`stop_checker.check_consecutive_unknown()`）
       - 将工具结果回灌 history（调用 `_append_tool_messages`）
       - 继续循环
     - 若 collector 无 tool_calls → 追加 assistant 消息到 history → yield `AgentDoneEvent(reason="natural_stop", ...)` → 退出
4. 实现 `_build_tools_map() -> dict[str, Tool]`：将 tools 列表转为 `{name: tool}` 字典
5. 实现 `_append_tool_messages(history, call, result)`：按协议格式追加（复用现有 chat.py 中的 `_append_tool_messages` 逻辑）

**验证：** `python -c "from poorcode.agent.loop import AgentLoop; print('ok')"` 无报错

## T7: Agent 包初始化

**文件：** `poorcode/agent/__init__.py`（新建）

**依赖：** T6

**步骤：**
1. 导入并导出 `AgentLoop`、`StreamingCollector`、`ToolExecutor`、`StopChecker`
2. 导入并导出所有 `AgentEvent` 类型

**验证：** `python -c "from poorcode.agent import AgentLoop, AgentProgressEvent, AgentDoneEvent"` 无报错

## T8: 配置新增 max_iterations

**文件：** `poorcode/config.py`、`config.yaml`

**依赖：** 无

**步骤：**
1. 在 `config.yaml` 中添加 `max_iterations: 25`
2. 在 `poorcode/config.py` 的 `Config` 数据类中添加 `max_iterations: int = 25`
3. 确认 YAML 解析时正确读入该字段

**验证：** `python -c "from poorcode.config import load_config; c = load_config(); print(c.max_iterations)"` 输出 `25`

## T9: TUI 适配 AgentEvent

**文件：** `poorcode/tui/app.py`、`poorcode/tui/render.py`

**依赖：** T2

**步骤：**
1. 在 `render.py` 中新增 `render_agent_progress(console, iteration, max_iterations)` —— 显示「🔄 第 3/25 轮」
2. 在 `render.py` 中新增 `render_agent_done(console, reason, total_iterations, tokens)` —— 显示停止原因摘要（如「✅ 完成（3 轮，1,234 tokens）」）
3. 在 `render.py` 中新增 `render_token_usage(console, input_tokens, output_tokens)` —— 显示单次调用的 Token 用量
4. 在 `app.py` 中新增 `show_agent_progress(iteration, max_iterations)` → 调用 `render_agent_progress`
5. 在 `app.py` 中新增 `show_agent_done(reason, total_iterations, input_tokens, output_tokens)` → 调用 `render_agent_done`
6. 在 `app.py` 中新增 `show_token_usage(input_tokens, output_tokens)` → 调用 `render_token_usage`
7. 保留现有的 `show_tool_status`、`stream_delta`、`finish_streaming` 等方法不变

**验证：** `python -c "from poorcode.tui.app import TuiApp; from poorcode.tui.render import render_agent_progress, render_agent_done; print('ok')"` 无报错

## T10: Chat Loop 重写为编排层 + Plan Mode

**文件：** `poorcode/chat.py`

**依赖：** T6、T7、T8、T9

**步骤：**
1. 导入 `AgentLoop`、`AgentEvent` 类型、`StopChecker`
2. 移除当前内联的工具调用处理逻辑（`_handle_tool_call`、`_append_tool_messages`、`_had_tool_call`），这些逻辑由 Agent Loop 内部处理
3. 新增 `AgentMode` 枚举：`PLAN`、`DO`，初始为 `DO`
4. 新增 `_get_tools_for_mode(mode: AgentMode) -> list[Tool]`：
   - `PLAN` → 筛选 category=="read" 的工具
   - `DO` → 全部工具
5. 新增 `_handle_command(user_input: str) -> tuple[bool, str]`：
   - `/plan` → 切换 mode=PLAN，返回 `(True, "已切换到 Plan Mode，仅可调研代码")`
   - `/do` → 切换 mode=DO，返回 `(True, "已切换到执行模式，可修改文件")`
   - `/quit`、`/exit` → 返回 `(True, "")`
   - 其他 → 返回 `(False, "")`
6. 重写 `run()` 函数：
   - 加载配置（含 `max_iterations`）
   - 创建 Provider，根据当前 mode 设置 `provider.tools`
   - 初始化 TUI
   - **主循环**：
     - 获取用户输入
     - 若为命令（`/plan`、`/do`、`/quit`），处理命令，显示提示，continue
     - 若为普通输入：
       - `tui.show_user_message(text)`
       - 追加到 history
       - `mode = DO` 时：全工具模式
       - `mode = PLAN` 时：筛选 tools 只含读类，重新设置 `provider.tools`
       - 创建 `AgentLoop(provider, tools, config.max_iterations)`
       - 消费 AgentEvent 流：
         - `text_delta` → `tui.begin_streaming()` + `tui.stream_delta()`
         - `tool_call` → 记录但不渲染（等 tool_result）
         - `tool_result` → `tui.show_tool_status(name, "done"/"error")`
         - `token_usage` → `tui.show_token_usage()`
         - `agent_progress` → `tui.show_agent_progress()`
         - `agent_done` → `tui.show_agent_done()` + 追加 assistant 消息到 history
         - `error` → `tui.show_error()`（可恢复的不中断，不可恢复的中断）
       - Agent Loop 结束后回到输入等待
7. 处理 `Esc`：在输入等待时用 `asyncio.Event` 作为取消标志传给 AgentLoop；`Ctrl+C` 退出程序
8. 移除旧有的 `_handle_tool_call`、`_append_tool_messages`、`_had_tool_call` 函数

**验证：** `python -m poorcode` 启动正常；输入「你好」→ 流式回复正常；输入 `/plan` → 显示模式切换提示；输入 `/do` → 切换回执行模式

## 执行顺序

```
Phase 1（并行，无依赖）
    T1 (category)  +  T2 (events)  +  T4 (stop)  +  T8 (config)
         │                  │              │              │
Phase 2（并行）              │              │              │
    T3 (collector, dep: T2) │              │              │
    T5 (executor, dep: T1, T2)            │              │
    T9 (TUI, dep: T2)                     │              │
         │                  │              │              │
Phase 3                      ↓              ↓              │
    T6 (loop, dep: T3 + T4 + T5)                          │
         │                                                 │
Phase 4   ↓                                                 │
    T7 (__init__, dep: T6)                                 │
         │                                                 │
Phase 5   ↓                                                 ↓
    T10 (chat rewrite, dep: T6 + T7 + T8 + T9)
```
