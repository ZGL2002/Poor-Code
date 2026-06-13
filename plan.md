# 工具系统 Plan

## 架构概览

当前五层架构中，工具系统作为一个新的横向层加入，位于 Chat Loop 编排层之下，与 Provider 层并列：

```
┌─────────────────────────────────────────────────────────────┐
│                       Chat Loop                              │  编排层
│                   (poorcode/chat.py)                         │  新增：工具调用检测→执行→结果注入
├──────────────────────────┬──────────────────────────────────┤
│       TUI 渲染层          │         Provider 抽象层           │
│  (poorcode/tui/)         │    (poorcode/provider/)          │
│  新增：show_tool_status   │   新增：工具格式转换、             │
│                          │   流式 tool_use 解析              │
├──────────────────────────┼──────────────────────────────────┤
│                          │        工具系统（新增）             │
│                          │    (poorcode/tools/)              │
│                          │    base.py → 抽象接口              │
│                          │    registry.py → 注册中心          │
│                          │    security.py → 路径校验          │
│                          │    read/write/edit/bash/glob/grep │
├──────────────────────────┴──────────────────────────────────┤
│                    HTTP + SSE 传输层                          │
│               (poorcode/provider/http.py)                    │
└─────────────────────────────────────────────────────────────┘
```

**各层职责变化：**

- **Chat Loop 编排层**：在流式循环中新增对 `tool_call` 事件的检测。收到工具调用后：暂停渲染 → 通知 TUI 展示状态 → 查 Registry 执行工具 → 结果构造成协议消息追加到 history → 再次调用 Provider 获取最终文本回复 → 停止（不循环）。
- **Provider 抽象层**：`LLMProvider.__init__()` 新增可选 `tools` 参数。各子类负责将工具列表转为协议格式、解析流式 tool_use 事件为统一的 `ToolCallRequest`。
- **TUI 渲染层**：新增 `show_tool_status(name, status)` 方法，在状态栏上方展示工具执行状态行。
- **工具系统（新增）**：Tool 抽象基类、注册中心、六个工具实现、路径安全校验。

## 核心数据结构

### ToolResult
工具执行结果，不论成功失败都返回此结构。

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 执行是否成功 |
| content | str | 成功时的返回数据，或失败时的错误描述 |
| error | str \| None | 失败时的简短错误码（如 "timeout"、"not_found"），成功时为 None |

### ToolContext
工具执行时的上下文信息，由 Chat Loop 注入。

| 字段 | 类型 | 说明 |
|------|------|------|
| cwd | Path | 当前工作目录（用于路径解析和安全校验） |
| timeout | float | 本工具的执行超时秒数 |

### Tool（抽象基类）

```python
class Tool(ABC):
    name: str           # 工具名，如 "read"、"bash"
    description: str    # 用途描述，供模型决策时参考
    parameters: dict    # JSON Schema 格式的参数定义

    @abstractmethod
    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """执行工具，params 由模型填入，context 由 Chat Loop 注入."""
```

- `parameters` 示例（Read 工具）：
  ```python
  {
      "type": "object",
      "properties": {
          "file_path": {"type": "string", "description": "文件路径，相对于工作目录"}
      },
      "required": ["file_path"]
  }
  ```

### ToolCallRequest
Provider 解析完流式 tool_use 事件后产出的统一结构。

| 字段 | 类型 | 说明 |
|------|------|------|
| tool_name | str | 要调用的工具名 |
| tool_input | dict | 模型填入的参数，键值对 |
| tool_use_id | str | 协议层的调用 ID（Anthropic 需要，OpenAI 需要） |

### StreamEvent 扩展
现有 StreamEvent 新增两种 type 值：

| type 值 | 含义 | content 字段 |
|---------|------|-------------|
| `"tool_call"` | 流式工具调用参数接收完毕 | ToolCallRequest 的 JSON 序列化字符串 |
| `"tool_error"` | 工具调用解析失败（多工具等） | 错误描述文本 |

## 模块设计

### 模块 A: Tool 抽象基类 (`poorcode/tools/base.py`)

**职责：** 定义 Tool 接口和工具系统核心数据结构  
**对外接口：**
- `ToolResult` — dataclass，字段 `success: bool`、`content: str`、`error: str | None`
- `ToolContext` — dataclass，字段 `cwd: Path`、`timeout: float`
- `Tool` — ABC，类属性 `name: str`、`description: str`、`parameters: dict`；抽象方法 `async execute(params: dict, context: ToolContext) -> ToolResult`

**依赖：** 无  
**对应需求：** F1

### 模块 B: 工具注册中心 (`poorcode/tools/registry.py`)

**职责：** 维护工具名到工具实例的映射，提供查找和协议格式转换  
**对外接口：**
- `register(tool: Tool) -> None` — 注册一个工具实例
- `get(name: str) -> Tool | None` — 按名查找
- `list_tools() -> list[Tool]` — 返回全部已注册工具
- `to_anthropic_format() -> list[dict]` — 转为 Anthropic Messages API 的 `tools` 数组格式
- `to_openai_format() -> list[dict]` — 转为 OpenAI Chat Completions 的 `tools` 数组格式

**格式转换要点：**
- Anthropic：`{"name": t.name, "description": t.description, "input_schema": t.parameters}`
- OpenAI：`{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}`

**依赖：** `poorcode/tools/base.py`  
**对应需求：** F2

### 模块 C: 路径安全 (`poorcode/tools/security.py`)

**职责：** 校验文件操作路径在工作目录范围内  
**对外接口：**
- `validate_path(file_path: str, cwd: Path) -> Path` — 解析相对路径，检查不越界。成功返回绝对路径，越界抛出 `PathSecurityError`
- `PathSecurityError` — 继承 `ValueError`，含中文错误描述

**校验逻辑：** `Path(cwd / file_path).resolve()` 后检查是否以 `cwd.resolve()` 开头。`file_path` 为绝对路径时直接拒绝。

**依赖：** 无  
**对应需求：** F7

### 模块 D: 六个核心工具

#### D1: Read (`poorcode/tools/read.py`)
**对外接口：** `class ReadTool(Tool)`，name=`"read"`，parameters 含 `file_path: string`  
**实现：** `validate_path()` → `Path.read_text()` → 返回文件内容和行数。文件不存在时返回 `success=False`  
**默认超时：** 30 秒（继承默认）  
**对应需求：** F3a

#### D2: Write (`poorcode/tools/write.py`)
**对外接口：** `class WriteTool(Tool)`，name=`"write"`，parameters 含 `file_path: string`、`content: string`  
**实现：** `validate_path()` → 父目录 `mkdir(parents=True)` → `Path.write_text()` → 返回路径和字节数  
**默认超时：** 30 秒  
**对应需求：** F3b

#### D3: Edit (`poorcode/tools/edit.py`)
**对外接口：** `class EditTool(Tool)`，name=`"edit"`，parameters 含 `file_path: string`、`old_string: string`、`new_string: string`  
**实现：** `validate_path()` → `Path.read_text()` → `str.count(old_string)` → 0 次返回 not_found，>1 次返回不唯一（含行号上下文），==1 次执行 `str.replace()` 并写回  
**默认超时：** 30 秒  
**对应需求：** F3c

#### D4: Bash (`poorcode/tools/bash.py`)
**对外接口：** `class BashTool(Tool)`，name=`"bash"`，parameters 含 `command: string`  
**实现：** `asyncio.create_subprocess_shell()` → 等待完成（timeout 控制）→ 返回 stdout、stderr、exit_code  
**路径限制：** 不做路径校验  
**默认超时：** 120 秒（覆盖默认 30 秒）  
**对应需求：** F3d

#### D5: Glob (`poorcode/tools/glob.py`)
**对外接口：** `class GlobTool(Tool)`，name=`"glob"`，parameters 含 `pattern: string`  
**实现：** `validate_path()` → `Path.glob(pattern)` → 返回匹配的相对路径列表  
**默认超时：** 30 秒  
**对应需求：** F3e

#### D6: Grep (`poorcode/tools/grep.py`)
**对外接口：** `class GrepTool(Tool)`，name=`"grep"`，parameters 含 `pattern: string`、`path: string?`、`glob: string?`  
**实现：** 在指定目录（默认 cwd）下递归搜索，用 glob 过滤文件名，逐行匹配 pattern（正则）。返回 `[{file, line_num, text}]` 列表  
**默认超时：** 30 秒  
**对应需求：** F3f

### 模块 E: Provider 层变更

#### E1: `poorcode/provider/base.py`
**变更：** 新增 `ToolCallRequest` 数据类；`StreamEvent` 注释新增 `tool_call` 和 `tool_error` type 值；`LLMProvider.__init__()` 新增可选参数 `tools: list[Tool] | None = None`，chat() 签名不变

#### E2: `poorcode/provider/anthropic.py`
**变更：**
- `_build_body()` → 当 `self.tools` 非空时注入 `"tools"` 字段（调用 `registry.to_anthropic_format()`）
- `chat()` → 新增 tool_use 流式解析状态机：收到 `content_block_start(type=tool_use)` 开始累积 → `content_block_delta(input_json_delta)` 拼接 JSON 字符串 → `content_block_stop` 时 parse 完整 JSON 产出 `StreamEvent(type="tool_call", content=ToolCallRequest.json())`
- 检测到多个 tool_use content block 时，只解析第一个并产出 `tool_error` 事件
- 工具执行后将结果构造成 Anthropic 的 `tool_result` content block，以 `role: user` 消息追加到历史

#### E3: `poorcode/provider/openai.py`
**变更：**
- `_build_body()` → 当 `self.tools` 非空时注入 `"tools"` 字段（调用 `registry.to_openai_format()`）
- `chat()` → 新增 tool_calls 流式解析：累积 `choices[0].delta.tool_calls` 碎片（按 index 分组）→ finishing 时产出 `StreamEvent(type="tool_call", ...)`
- 检测到多个 tool_calls 时只执行第一个并产出错
- 工具执行后将结果以 `role: tool` + `tool_call_id` 消息追加到历史

### 模块 F: TUI 层变更 (`poorcode/tui/app.py`)

**对外接口：**
- `show_tool_status(name: str, status: str) -> None` — status 取值 `"running"`、`"done"`、`"error"`。在对话区渲染一行状态，更新为最终结果
- 修改 `finish_streaming()` → 接受可选 `interrupted_by_tool: bool` 参数，为 True 时不渲染 Markdown（工具调用不是文本回复）

### 模块 G: Chat Loop 变更 (`poorcode/chat.py`)

**变更要点：**
1. `run()` 中创建 Provider 后，将已注册工具列表传给 Provider 构造函数
2. 流式循环中新增对 `tool_call` 和 `tool_error` 事件的处理：
   - `tool_error` → `tui.show_error()` + 追加错误消息到 history，继续下一轮
   - `tool_call` → 解析 `ToolCallRequest` → `tui.show_tool_status(name, "running")` → 从 Registry 查工具 → 创建 `ToolContext(cwd, timeout)` → `await tool.execute(params, context)` → `tui.show_tool_status(name, "done"/"error")` → 构造协议消息追加到 history → 第二次调用 `provider.chat()` 获取最终文本回复 → 流式展示 → 停止
3. 最终文本回复后不再调用工具（即使模型返回了新的 tool_use，忽略/报错）

## 模块交互

### 一次工具调用的完整链路

```
用户输入「读一下 README.md」
    │
    ▼
chat.py: history.append(Message("user", "读一下 README.md"))
    │
    ├─ provider.chat(messages=history)         ← 发起流式请求（body 含 tools 列表）
    │       │
    │       ├─ anthropic.py: _build_body()     ← 注入 "tools" 字段
    │       ├─ http.post_sse()                 ← 发送 POST，SSE 流读取
    │       │
    │       └─ 流式解析：
    │           content_block_start(type=tool_use) → 初始化累积状态
    │           content_block_delta(input_json_delta) → 拼接 JSON 碎片
    │           content_block_stop → parse 完整参数
    │               │
    │               └─ yield StreamEvent(type="tool_call", content="{...}")
    │
    ├─ chat.py 收到 tool_call 事件：
    │     │
    │     ├─ 解析 ToolCallRequest(tool_name="read", tool_input={"file_path": "README.md"})
    │     ├─ tui.show_tool_status("read", "running")    ← 终端显示 🔧 read … ⏳
    │     ├─ tool = registry.get("read")
    │     ├─ context = ToolContext(cwd=Path.cwd(), timeout=30)
    │     ├─ result = await tool.execute({"file_path": "README.md"}, context)
    │     │       │
    │     │       ├─ security.validate_path("README.md", cwd)  ← 路径校验
    │     │       └─ Path.read_text()                          ← 读文件
    │     │
    │     ├─ result = ToolResult(success=True, content="...文件内容...", error=None)
    │     ├─ tui.show_tool_status("read", "done")      ← 终端显示 🔧 read … ✅
    │     │
    │     └─ 构造工具结果消息追加到 history：
    │           Anthropic: Message(role="user", content=[{"type": "tool_result", ...}])
    │           (由 Provider 的工具结果格式化方法完成)
    │
    ├─ provider.chat(messages=history)         ← 第二次调用，携带工具结果
    │       │
    │       └─ 模型看到文件内容，生成文本回复
    │           yield StreamEvent(type="text_delta", ...)
    │           yield StreamEvent(type="done")
    │
    └─ chat.py:
          ├─ tui.stream_delta() / tui.finish_streaming()
          ├─ history.append(Message("assistant", full_response))
          └─ 停止，等待用户下一轮输入（不检查新 tool_use）
```

### 多工具调用被拒绝的流程

```
provider.chat() 解析到 2 个 tool_use content block
    │
    └─ 只解析第一个，产出:
        1. StreamEvent(type="tool_call", content=ToolCallRequest{第1个工具})
        2. StreamEvent(type="tool_error", content="模型请求了 2 个工具，本次仅支持 1 个。仅执行第 1 个。")

chat.py:
    ├─ 收到 tool_call → 正常执行第 1 个工具
    └─ 收到 tool_error → tui.show_error("模型请求了多个工具...")
```

### 数据流方向

```
config.yaml ──→ ProviderConfig ──→ LLMProvider(..., tools=registry.list_tools())
                                            │
registry ──→ to_anthropic_format() ────────→ chat() body["tools"]
registry ──→ to_openai_format() ────────────→ chat() body["tools"]
                                            │
chat() SSE response ──→ ToolCallRequest ──→ registry.get(name).execute()
                                            │
tool.execute() ──→ ToolResult ──→ history (protocol-formatted message)
                                            │
history ──→ provider.chat(messages=history) ──→ 最终文本回复 ──→ TUI
```

### 状态机：Provider 流式解析中的 tool_use 跟踪

```
初始状态: TEXT_MODE
    │
    ├─ content_block_start(type=text) → 保持 TEXT
    ├─ content_block_start(type=tool_use) → 进入 TOOL_MODE
    │       │
    │       └─ 记录 tool_use_id, tool_name (从 content_block 中)
    │
    ├─ TOOL_MODE:
    │     ├─ content_block_delta(input_json_delta) → 累积 JSON 片段
    │     └─ content_block_stop → 解析累积的 JSON
    │           ├─ 成功 → yield StreamEvent("tool_call", ...)
    │           └─ 失败 → yield StreamEvent("tool_error", "JSON 解析失败")
    │
    └─ 检测到第 2 个 tool_use content block → 忽略 + yield StreamEvent("tool_error", ...)
```

## 文件组织

```
Poor Code/
├── poorcode/
│   ├── __init__.py
│   ├── __main__.py
│   ├── chat.py                    — 修改：工具调用检测与执行编排
│   ├── config.py
│   ├── tools/                     — 新建包
│   │   ├── __init__.py            — 导出 + 启动时自动注册全部六个工具
│   │   ├── base.py                — Tool ABC、ToolResult、ToolContext
│   │   ├── registry.py            — 注册中心 + 协议格式转换
│   │   ├── security.py            — 路径安全校验
│   │   ├── read.py                — Read 工具
│   │   ├── write.py               — Write 工具
│   │   ├── edit.py                — Edit 工具
│   │   ├── bash.py                — Bash 工具
│   │   ├── glob.py                — Glob 工具
│   │   └── grep.py                — Grep 工具
│   ├── provider/
│   │   ├── __init__.py
│   │   ├── base.py                — 修改：新增 ToolCallRequest；LLMProvider.__init__ 加 tools 参数
│   │   ├── registry.py
│   │   ├── anthropic.py           — 修改：tool_use 流式解析 + 工具结果格式化
│   │   ├── openai.py              — 修改：tool_calls 流式解析 + 工具结果格式化
│   │   └── http.py
│   └── tui/
│       ├── __init__.py
│       ├── app.py                 — 修改：新增 show_tool_status()
│       ├── render.py              — 修改：新增 render_tool_status()
│       └── input_area.py
├── spec.md
├── plan.md
├── task.md
├── checklist.md
├── pyproject.toml
└── README.md
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 工具传递给 Provider 的方式 | `__init__(tools=...)` 而非 `chat(tools=...)` | 维持 `chat()` 签名不变（N3），工具集合在 Provider 生命周期内不变，放构造函数更合理 |
| 流式工具调用解析策略 | Provider 内部累积 JSON 碎片，完整后一次性产出 `tool_call` 事件 | Chat Loop 不需要理解协议细节（F4 与 F5 解耦）。Provider 层做协议适配，Chat Loop 只看到统一的 `ToolCallRequest` |
| Tool 参数定义格式 | 原生 dict（JSON Schema） | 无额外依赖，与两种协议的 `input_schema`/`parameters` 字段天然兼容。Provider 的 `to_*_format()` 直接透传 |
| Edit 匹配策略 | `str.count()` + `str.replace()` | Python 标准库即可完成精确匹配，无需 difflib 或第三方 diff 库。先 count 再 replace 保证原子性 |
| Bash 超时默认值 | 120 秒 | 编译、测试等常见命令可能耗时较长，30 秒不够。长超时配合 asyncio.wait_for 实现中断 |
| 路径安全实现 | `Path.resolve()` 后前缀比较 | 正确处理 `..`、符号链接等越界手段。绝对路径直接拒绝，不尝试 normalize |
| 工具结果截断 | 100KB 硬截，附加 `...(已截断)` 提示 | 防止大文件内容撑爆上下文窗口。100KB 约 25K token，足够模型理解但仍需设限 |
| 多工具检测位置 | Provider 层检测 + Chat Loop 兜底 | 双重保障。Provider 在解析时计数 tool_use content block 数量，Chat Loop 在收到 tool_call 后检查是否有后续 tool_call（异常情况） |
| Chat Loop 第二次 chat 后处理 | 忽略新的 tool_use，只取 text_delta | 不在本次实现 Agent Loop。如果模型在第二次回复中又请求工具，忽略并提示用户「模型尝试再次调用工具，当前版本不支持」 |
| 工具注册时机 | `poorcode/tools/__init__.py` 导入时自动注册 | 与 Provider 注册机制一致（`poorcode/provider/__init__.py` 模式）。只要 import poorcode.tools 就完成注册 |

### spec 覆盖检查

| F 需求 | 对应模块 |
|--------|---------|
| F1 Tool 抽象接口 | `tools/base.py` |
| F2 工具注册中心 | `tools/registry.py` |
| F3 六个核心工具 | `tools/read.py` ~ `grep.py` |
| F4 流式工具调用解析 | `provider/anthropic.py` + `provider/openai.py` |
| F5 工具执行与结果回灌 | `chat.py` + Provider 结果格式化 |
| F6 超时与错误处理 | `chat.py` 执行层 + 各工具 `execute()` |
| F7 路径安全 | `tools/security.py` |
| F8 TUI 工具状态展示 | `tui/app.py` + `tui/render.py` |
