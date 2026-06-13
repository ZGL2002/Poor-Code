# 工具系统 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `poorcode/tools/__init__.py` | 导出 + 启动时自动注册全部六个工具 |
| 新建 | `poorcode/tools/base.py` | Tool ABC、ToolResult、ToolContext |
| 新建 | `poorcode/tools/registry.py` | 注册中心 + 协议格式转换 |
| 新建 | `poorcode/tools/security.py` | 路径安全校验 |
| 新建 | `poorcode/tools/read.py` | Read 工具 |
| 新建 | `poorcode/tools/write.py` | Write 工具 |
| 新建 | `poorcode/tools/edit.py` | Edit 工具 |
| 新建 | `poorcode/tools/bash.py` | Bash 工具 |
| 新建 | `poorcode/tools/glob.py` | Glob 工具 |
| 新建 | `poorcode/tools/grep.py` | Grep 工具 |
| 修改 | `poorcode/provider/base.py` | 新增 ToolCallRequest；LLMProvider 加 tools 参数 |
| 修改 | `poorcode/provider/anthropic.py` | tool_use 流式解析 + 工具结果格式化 |
| 修改 | `poorcode/provider/openai.py` | tool_calls 流式解析 + 工具结果格式化 |
| 修改 | `poorcode/tui/render.py` | 新增 render_tool_status() |
| 修改 | `poorcode/tui/app.py` | 新增 show_tool_status()；finish_streaming 适配工具调用 |
| 修改 | `poorcode/chat.py` | 工具调用检测与执行编排 |

## T1: Tool 抽象基类与数据结构

**文件：** `poorcode/tools/base.py`
**依赖：** 无
**步骤：**
1. 定义 `ToolResult` 数据类（`success: bool`、`content: str`、`error: str | None`）
2. 定义 `ToolContext` 数据类（`cwd: Path`、`timeout: float`）
3. 定义 `Tool` 抽象基类，含类属性 `name: str`、`description: str`、`parameters: dict`
4. 声明抽象方法 `async execute(self, params: dict, context: ToolContext) -> ToolResult`
5. 添加 RESULT_MAX_SIZE = 100 * 1024 常量（100KB 截断阈值）

**验证：** `python -c "from poorcode.tools.base import Tool, ToolResult, ToolContext"` 无报错

## T2: 路径安全校验

**文件：** `poorcode/tools/security.py`
**依赖：** 无
**步骤：**
1. 定义 `PathSecurityError`，继承 `ValueError`
2. 实现 `validate_path(file_path: str, cwd: Path) -> Path`：
   - `file_path` 为绝对路径时抛出 `PathSecurityError("不允许绝对路径：{file_path}")`
   - `Path(cwd / file_path).resolve()` 获取绝对路径
   - 检查是否以 `cwd.resolve()` 开头，不是则抛出 `PathSecurityError("路径越界：...")`
   - 通过则返回解析后的 `Path`

**验证：** 临时脚本测试：`validate_path("foo.txt", cwd)` 正常返回；`validate_path("/etc/passwd", cwd)` 抛异常；`validate_path("../outside", cwd)` 抛异常

## T3: 工具注册中心

**文件：** `poorcode/tools/registry.py`
**依赖：** T1
**步骤：**
1. 维护模块级 `_registry: dict[str, Tool]` 字典
2. 实现 `register(tool: Tool)`——按 `tool.name` 注册
3. 实现 `get(name: str) -> Tool | None`
4. 实现 `list_tools() -> list[Tool]`——返回全部已注册工具
5. 实现 `to_anthropic_format() -> list[dict]`——每条 `{"name": t.name, "description": t.description, "input_schema": t.parameters}`
6. 实现 `to_openai_format() -> list[dict]`——每条 `{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}`

**验证：** 创建 MockTool 注册后，`get("mock")` 能找到，`list_tools()` 含它，`to_anthropic_format()` / `to_openai_format()` 输出格式正确

## T4: Read 工具

**文件：** `poorcode/tools/read.py`
**依赖：** T1, T2
**步骤：**
1. 实现 `ReadTool(Tool)`，name=`"read"`，description 说明用途，parameters 定义 `file_path` 参数
2. `execute()` 中调用 `validate_path()` → `Path.read_text()` → 返回文件内容和行数
3. 超过 100KB 时截断并附加 `\n...(内容已截断，超过 100KB)`
4. `FileNotFoundError` 时返回 `ToolResult(success=False, error="not_found", content="文件不存在：{path}")`
5. `PermissionError` 时返回 `ToolResult(success=False, error="permission", content="...")`

**验证：** 临时脚本：读存在的文件 → `success=True`；读不存在的文件 → `success=False` + error="not_found"

## T5: Write 工具

**文件：** `poorcode/tools/write.py`
**依赖：** T1, T2
**步骤：**
1. 实现 `WriteTool(Tool)`，name=`"write"`，parameters 含 `file_path` 和 `content`
2. `execute()` 中调用 `validate_path()` → `parent.mkdir(parents=True, exist_ok=True)` → `Path.write_text()`
3. 返回 `ToolResult(success=True, content="已写入：{path}，{bytes} 字节")`
4. 异常时返回 `success=False`

**验证：** 临时脚本写入文件 → 检查文件存在且内容正确

## T6: Edit 工具

**文件：** `poorcode/tools/edit.py`
**依赖：** T1, T2
**步骤：**
1. 实现 `EditTool(Tool)`，name=`"edit"`，parameters 含 `file_path`、`old_string`、`new_string`
2. `execute()` 逻辑：
   - `validate_path()` → `Path.read_text()`
   - `count = content.count(old_string)`
   - `count == 0` → 返回 `success=False, error="not_found", content="未找到原文，请确认字符串内容与文件一致"`
   - `count > 1` → 返回 `success=False, error="not_unique", content="匹配到 N 处，原文不唯一：\n（列出每处的行号与上下文）"`
   - `count == 1` → `content.replace(old_string, new_string)` → `Path.write_text()` → 返回 `success=True, content="已替换 1 处"`
3. 替换成功后返回文件路径和替换位置简要信息

**验证：** 临时脚本：唯一匹配替换成功；不匹配返回 not_found；多处匹配返回 not_unique

## T7: Bash 工具

**文件：** `poorcode/tools/bash.py`
**依赖：** T1
**步骤：**
1. 实现 `BashTool(Tool)`，name=`"bash"`，parameters 含 `command`，覆盖默认超时 120 秒
2. `execute()` 逻辑：
   - `asyncio.wait_for(asyncio.create_subprocess_shell(cmd, stdout=PIPE, stderr=PIPE), timeout=context.timeout)`
   - 等待进程完成，收集 stdout、stderr、exit_code
   - 返回 `success=True`（exit_code==0）或 `success=False`（exit_code!=0），content 含 stdout + stderr
3. `asyncio.TimeoutError` → 杀进程，返回 `success=False, error="timeout"`
4. 不调用 `validate_path()`（Bash 无路径限制）

**验证：** 临时脚本：`command="echo hello"` → success=True，stdout="hello\n"；`command="sleep 5"` + timeout=1 → success=False, error="timeout"

## T8: Glob 工具

**文件：** `poorcode/tools/glob.py`
**依赖：** T1, T2
**步骤：**
1. 实现 `GlobTool(Tool)`，name=`"glob"`，parameters 含 `pattern`
2. `execute()` 逻辑：
   - `validate_path(".", cwd)` 确认基准目录可访问（pattern 本身不校验越界，由 glob 结果各自校验）
   - `Path.glob(pattern)` 收集匹配结果
   - 结果使用相对路径展示
   - 无匹配时返回 `content="未找到匹配的文件"`
3. 结果过多时截断到 200 条，附加提示

**验证：** 临时脚本：`pattern="**/*.py"` → 返回 .py 文件列表

## T9: Grep 工具

**文件：** `poorcode/tools/grep.py`
**依赖：** T1, T2
**步骤：**
1. 实现 `GrepTool(Tool)`，name=`"grep"`，parameters 含 `pattern`（必填）、`path`（可选）、`glob`（可选）
2. `execute()` 逻辑：
   - 确定搜索目录：`path` 存在则 `validate_path(path)`，否则用 cwd
   - 若 `glob` 存在，先用 `Path.rglob(glob)` 筛选文件
   - 否则递归遍历所有文本文件（跳过二进制和隐藏目录 `.git` 等）
   - 逐行用 `re.search(pattern, line)` 匹配
   - 返回 `[{file, line_num, text}]` 格式
3. 结果过多时截断到 500 行，附加提示
4. 编译正则异常时返回 `success=False`

**验证：** 临时脚本：`pattern="import"` → 返回所有含 import 的文件和行

## T10: 工具包初始化与自动注册

**文件：** `poorcode/tools/__init__.py`
**依赖：** T3, T4, T5, T6, T7, T8, T9
**步骤：**
1. 导入所有工具类和注册中心函数
2. 模块加载时调用 `register(ReadTool())` 等六行完成注册
3. 导出 `Tool`、`ToolResult`、`ToolContext`、`register`、`get`、`list_tools`、`to_anthropic_format`、`to_openai_format`

**验证：** `python -c "from poorcode.tools import list_tools; print([t.name for t in list_tools()])"` 输出 `['read', 'write', 'edit', 'bash', 'glob', 'grep']`

## T11: Provider 基类变更

**文件：** `poorcode/provider/base.py`
**依赖：** T1（Tool 类型）
**步骤：**
1. 新增 `ToolCallRequest` 数据类（`tool_name: str`、`tool_input: dict`、`tool_use_id: str`）
2. 在 `LLMProvider.__init__` 中新增可选参数 `tools: list | None = None`，保存为 `self.tools`
3. `StreamEvent` 注释补充 `tool_call` 和 `tool_error` 两种 type 值
4. `chat()` 签名不变

**验证：** `python -c "from poorcode.provider.base import ToolCallRequest, LLMProvider"` 无报错；`LLMProvider(config, tools=[])` 正常实例化

## T12: Anthropic Provider 工具调用支持

**文件：** `poorcode/provider/anthropic.py`
**依赖：** T11
**步骤：**
1. `_build_body()` → 当 `self.tools` 非空时，调用 `to_anthropic_format()` 注入 `"tools"` 字段
2. `chat()` 中新增 tool_use 流式解析状态机：
   - 用 `_tool_use_count` 计数 content_block_start(type=tool_use)
   - 用 `_tool_use_buffer` 累积 input_json_delta 的 `partial_json` 片段
   - 用 `_current_tool_name`、`_current_tool_id` 记录当前工具信息
   - `content_block_stop` 时：若为 tool_use block → 解析累积 JSON → yield `StreamEvent("tool_call", ToolCallRequest(...).json())`
   - 当 `_tool_use_count > 1` 时，产出额外的 `StreamEvent("tool_error", "模型请求了 N 个工具...")`
3. 新增 `format_tool_result(tool_use_id, tool_result: ToolResult) -> dict` 静态方法，返回 Anthropic 格式的 tool_result content block
4. 新增 `build_tool_result_message(tool_use_id, tool_result) -> Message`，返回 `Message(role="user", content=[tool_result_block])`

**验证：** 暂不独立运行，待 T16 通过 chat loop 整体验证

## T13: OpenAI Provider 工具调用支持

**文件：** `poorcode/provider/openai.py`
**依赖：** T11
**步骤：**
1. `_build_body()` → 当 `self.tools` 非空时，调用 `to_openai_format()` 注入 `"tools"` 字段
2. `chat()` 中新增 tool_calls 流式解析：
   - 在现有 delta 解析中增加 `delta.get("tool_calls")` 处理
   - 按 `tool_calls[].index` 分组累积（用 dict 维护 index → {id, function_name, function_arguments}）
   - `finish_reason` 出现时：检查累积的 tool_calls，产出 `StreamEvent("tool_call", ...)`
   - 多个 tool_calls（len > 1）时只取第一个并产出 `tool_error`
3. 若有 `finish_reason == "tool_calls"`，产出 tool_call 事件后不应再产出 text_delta 的 done
4. 新增 `format_tool_result(tool_call_id, tool_result)` → `Message(role="tool", content=..., tool_call_id=...)`

**验证：** 暂不独立运行，待 T16 整体验证

## T14: TUI 渲染——工具状态行

**文件：** `poorcode/tui/render.py`
**依赖：** 无（仅依赖 rich）
**步骤：**
1. 实现 `render_tool_status(console, tool_name, status, detail="")`
   - `status="running"` → 显示 `🔧 {tool_name} … ⏳ 执行中`（黄色）
   - `status="done"` → 显示 `🔧 {tool_name} … ✅ 完成`（绿色）
   - `status="error"` → 显示 `🔧 {tool_name} … ❌ {detail}`（红色）
2. 使用 Rich 的 `Text` 或直接 `console.print()` 渲染一行

**验证：** 临时脚本调用三种状态，观察终端输出颜色和图标是否正确

## T15: TuiApp 工具状态方法

**文件：** `poorcode/tui/app.py`
**依赖：** T14
**步骤：**
1. 新增 `show_tool_status(name, status, detail="")`——调用 `render_tool_status()`
2. 修改 `finish_streaming()`——不再默认渲染 Markdown。当流式结束没有 full_text 时（工具调用场景），仅更新状态栏
3. 新增 `finish_tool_response(full_text)`——工具调用后的回复渲染（本质上复用 finish_streaming 的 Markdown 渲染逻辑，但不做流式 Live 清理）

**验证：** 实例化 TuiApp → 调用 `show_tool_status("read", "running")` → `show_tool_status("read", "done")` → 观察终端输出

## T16: Chat Loop 工具调用编排

**文件：** `poorcode/chat.py`
**依赖：** T3, T10, T12, T13, T15
**步骤：**
1. 导入 `poorcode.tools`（触发自动注册）和 `ToolContext`、`ToolResult`
2. `run()` 中创建 Provider 后，`provider = create_provider(config)` → `provider.tools = list_tools()`（或通过构造函数传入）
3. 流式循环中新增事件处理：
   - `event.type == "tool_error"` → `tui.show_error(event.content)`，追加提示到 history，continue 下一轮
   - `event.type == "tool_call"` → 解析 `ToolCallRequest`：
     a. `tui.show_tool_status(name, "running")`
     b. `tool = registry.get(tool_name)`，若找不到 → `tui.show_tool_status(name, "error", "工具未注册")` + 返回错误给模型
     c. 构造 `ToolContext(cwd=Path.cwd(), timeout=tool.default_timeout)`
     d. `result = await tool.execute(tool_input, context)`
     e. `tui.show_tool_status(name, "done" if result.success else "error", result.error or "")`
     f. 调用 `provider.format_tool_result()` 构造协议消息，追加到 history
     g. 第二次调用 `provider.chat(messages=history)`，流式渲染文本回复
     h. 追加 assistant Message 到 history，本次循环结束（不检查新 tool_use）
4. 注意：工具调用后的第二次 chat 中若出现新的 `tool_call`，产出 `tool_error` 而非继续执行
5. 工具执行期间捕获异常，转为 `ToolResult(success=False, ...)` 不崩溃

**验证：** 配置有效 API Key 后启动，输入「读一下 README.md」，观察工具调用→执行→回复的完整流程

## T17: Provider 包初始化更新（如需）

**文件：** `poorcode/provider/__init__.py`
**依赖：** T12, T13
**步骤：**
1. 确认 `__all__` 导出列表包含 `ToolCallRequest`（如果 chat.py 需要从此导入）

**验证：** `python -c "from poorcode.provider import ToolCallRequest, LLMProvider, create_provider"` 无报错

## 执行顺序

```
T1 (Tool 抽象基类)
 │
 ├── T2 (路径安全) ──┬── T4 (Read) ──────────┐
 │                   ├── T5 (Write)            │
 │                   ├── T6 (Edit)             ├── T10 (工具包初始化)
 │                   ├── T8 (Glob)             │
 │                   └── T9 (Grep)             │
 │                                             │
 ├── T3 (注册中心) ────────────────────────────┤
 │                                             │
 └── T7 (Bash) ───────────────────────────────┘

T11 (Provider 基类变更)
 │
 ├── T12 (Anthropic 工具解析) ──┐
 │                              ├── T17 (Provider 包更新)
 └── T13 (OpenAI 工具解析) ────┘

T14 (render_tool_status) ── T15 (TuiApp 工具方法)

T10 + T15 + T12 + T13 + T17 ──── T16 (Chat Loop 编排)
```

- T2, T3, T7 在 T1 完成后可并行
- T4-T6, T8-T9 在 T2 完成后可并行
- T12, T13 在 T11 完成后可并行
- T14 独立可并行
- T16 是最后集线器，依赖 T10, T12, T13, T15
