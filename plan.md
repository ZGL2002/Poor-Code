# Agent Loop Plan

## 架构概览

新增 `poorcode/agent/` 模块，将当前 `chat.py` 中嵌入的循环逻辑抽取为独立的 Agent Loop 引擎。架构分为三层：

### 第一层：Agent Loop 引擎（`poorcode/agent/loop.py`）

ReAct 循环核心。接收对话历史、Provider、工具列表，产出 `AgentEvent` 流。循环内部依次：

1. 调用 Provider 流式对话
2. 流式收集器收集完整响应
3. 检查停止条件
4. 如有工具调用 → 工具执行器分批执行 → 结果回灌历史 → 回到步骤 1
5. 如无工具调用 → 自然结束，产出 `agent_done`

### 第二层：支撑组件（`poorcode/agent/` 内）

- **AgentEvent 类型**（`events.py`）— 将当前 `StreamEvent` 扩展为更丰富的事件集。保留 `text_delta`、`thinking_delta`，新增 `tool_result`、`token_usage`、`agent_progress`、`agent_done`
- **流式收集器**（`collector.py`）— 消费 Provider 产出的 `StreamEvent`，实时转发文本增量，同时累积完整文本和工具调用列表
- **工具执行器**（`executor.py`）— 接收工具调用列表，按副作用分类（读类并发、写类串行），执行后返回有序结果
- **停止条件检查器**（`stop.py`）— 统一的停止条件评估函数，返回停止原因或 None

### 第三层：编排层（`chat.py` 修改）

chat.py 不再内联循环逻辑，变为薄编排层：
- 初始化 Provider、Agent Loop、TUI
- 用户输入循环 → 追加到历史 → 调用 Agent Loop → 消费 AgentEvent 流 → 驱动 TUI
- 处理 `/plan`、`/do`、`/quit` 等用户命令

## 核心数据结构

### AgentEvent 体系

废弃当前 `StreamEvent` 的五种类型，定义更丰富的 `AgentEvent`。所有事件共用 `type` 字段区分，通过 dataclass 承载数据：

```
AgentEvent
├── text_delta          — 流式文本增量（content: str）
├── thinking_delta      — 思考增量（content: str）
├── tool_call           — 单个工具调用已就绪（tool_name, tool_input, tool_use_id）
├── tool_result        — 工具执行完成（tool_name, tool_use_id, success, error, content_preview）
├── token_usage        — 单次 LLM 调用的 Token 用量（input_tokens, output_tokens）
├── agent_progress     — 循环进度（iteration, max_iterations）
├── agent_done         — Agent Loop 结束（reason, total_iterations, token_usage）
└── error              — 错误事件（message, recoverable）
```

`StreamEvent` 保留在 Provider 层内部使用，Provider 的 `chat()` 仍然产出 `StreamEvent`。`StreamingCollector` 是 `StreamEvent` → `AgentEvent` 的转换层。

### Tool 安全分类

在 `Tool` 基类新增一个属性：

```
Tool.category: str  — "read" 或 "write"
```

各工具分类：

| 工具 | category |
|------|----------|
| Read | read |
| Glob | read |
| Grep | read |
| Write | write |
| Edit | write |
| Bash | write |

### Plan Mode 状态

简单的枚举，维护在编排层：

```
AgentMode: PLAN | DO
```

## 模块设计

### 模块 A：AgentEvent 定义（`poorcode/agent/events.py`）

**职责：** 定义所有 AgentEvent 数据类，提供类型提示和构造辅助

**对外接口：**
- 各事件 dataclass（`TextDeltaEvent`、`ToolCallEvent`、`ToolResultEvent`、`TokenUsageEvent`、`AgentProgressEvent`、`AgentDoneEvent`、`ErrorEvent`）
- 联合类型 `AgentEvent = TextDeltaEvent | ToolCallEvent | ...`

**依赖：** 无外部模块依赖

### 模块 B：流式收集器（`poorcode/agent/collector.py`）

**职责：** 消费 Provider 的 `AsyncIterator[StreamEvent]`，转为 `AsyncIterator[AgentEvent]`。实现双路——实时转发文本，同时累积完整响应

**对外接口：**
- `StreamingCollector` 类
- `collect(stream: AsyncIterator[StreamEvent]) -> AsyncIterator[AgentEvent]` — 异步生成器
- `full_text: str` 属性 — 累积的完整文本
- `tool_calls: list[ToolCallRequest]` 属性 — 累积的工具调用列表（按接收顺序）

**依赖：** `poorcode.provider.base.StreamEvent`、`poorcode.provider.base.ToolCallRequest`、`poorcode.agent.events`

### 模块 C：工具执行器（`poorcode/agent/executor.py`）

**职责：** 接收工具调用列表，按 category 分类，读类用 `asyncio.gather` 并发执行，写类串行执行

**对外接口：**
- `async execute_all(calls: list[ToolCallRequest], tools: dict[str, Tool], cwd: Path) -> list[tuple[ToolCallRequest, ToolResult]]` — 执行全部调用，返回调用与结果的配对列表，保持原始顺序
- `classify(calls: list[ToolCallRequest], tools: dict) -> tuple[list, list]` — 按读/写分类

**依赖：** `poorcode.tools.base.Tool, ToolContext, ToolResult`、`poorcode.provider.base.ToolCallRequest`

### 模块 D：停止条件检查器（`poorcode/agent/stop.py`）

**职责：** 评估当前 Agent Loop 状态，判断是否应停止

**对外接口：**
- `StopChecker` 类
- `check(iteration, tool_calls, consecutive_unknown, stream_error) -> str | None` — 返回停止原因或 None
- `reset()` — 重置内部状态（连续未知工具计数等）

**依赖：** 无外部模块依赖

### 模块 E：Agent Loop（`poorcode/agent/loop.py`）

**职责：** 编排 ReAct 循环，组合收集器、执行器、停止检查器

**对外接口：**
- `AgentLoop` 类
- `async run(history: list[Message], system_prompt: str | None = None) -> AsyncIterator[AgentEvent]` — 执行 Agent Loop，产出事件流

**依赖：** 上述全部 agent 子模块、Provider、工具注册表

### 模块 F：编排层（`poorcode/chat.py` 修改）

**职责：** 薄编排，处理用户输入/命令，组装 Agent Loop 调用，连接 TUI

**主要修改：**
- 用户命令解析（`/plan`、`/do`、`/quit`、`/exit`）
- 根据当前 `AgentMode` 筛选传给 Provider 的工具列表
- 调用 `AgentLoop.run()`，消费 `AgentEvent` 流驱动 TUI
- 处理 `Esc`（取消当前 Agent Loop）和 `Ctrl+C`（退出）

## 模块交互

一次用户输入触发的完整调用链：

```
chat.py (编排层)
  │
  ├─ 1. 解析用户输入
  │     /plan → agent_mode = PLAN, 跳过 LLM 调用
  │     /do   → agent_mode = DO,   跳过 LLM 调用
  │     普通输入 → 追加到 history，继续
  │
  ├─ 2. 根据 agent_mode 筛选工具列表
  │     PLAN → [Read, Glob, Grep]
  │     DO   → [Read, Write, Edit, Bash, Glob, Grep]
  │
  ├─ 3. 调用 AgentLoop.run(history, system_prompt)
  │     │
  │     ├─ 3.1 产出 agent_progress 事件
  │     │
  │     ├─ 3.2 调用 Provider.chat(messages=history, stream=True)
  │     │     ↓ StreamEvent 流
  │     ├─ 3.3 StreamingCollector.collect(stream)
  │     │     ├─ 实时转发 text_delta → TUI
  │     │     └─ 累积 full_text + tool_calls[]
  │     │
  │     ├─ 3.4 流结束后 StopChecker.check()
  │     │     有 tool_calls？
  │     │     ├─ 否 → 产出 agent_done ("natural_stop")
  │     │     └─ 是 → 继续
  │     │
  │     ├─ 3.5 ToolExecutor.execute_all(tool_calls)
  │     │     ├─ 分类：读类 + 写类
  │     │     ├─ 读类并发执行（asyncio.gather）
  │     │     ├─ 写类串行执行（for loop await）
  │     │     └─ 每个工具结果产出 tool_result 事件 → TUI
  │     │
  │     ├─ 3.6 工具结果回灌 history
  │     │
  │     ├─ 3.7 产出 token_usage 事件 → TUI
  │     │
  │     └─ 3.8 回到 3.1（除非停止条件触发）
  │
  ├─ 4. 产出 agent_done 事件 → TUI 展示停止原因
  │
  └─ 5. 回到用户输入等待
```

## 文件组织

```
poorcode/
├── agent/
│   ├── __init__.py        — 导出 AgentLoop、AgentEvent 类型、ToolExecutor
│   ├── events.py          — 全部 AgentEvent dataclass 定义
│   ├── collector.py       — StreamingCollector
│   ├── executor.py        — ToolExecutor（分类 + 并发/串行执行）
│   ├── stop.py            — StopChecker
│   └── loop.py            — AgentLoop 主循环编排
├── chat.py                — 编排层（重写，抽取循环逻辑到 agent/）
├── config.py              — 新增 max_iterations 配置项
├── config.yaml            — 新增 max_iterations: 25
├── provider/
│   ├── base.py            — 保留 StreamEvent/ToolCallRequest，不做破坏性修改
│   └── ...
├── tools/
│   ├── base.py            — Tool 基类新增 category 属性
│   ├── read.py            — category = "read"
│   ├── glob.py            — category = "read"
│   ├── grep.py            — category = "read"
│   ├── write.py           — category = "write"
│   ├── edit.py            — category = "write"
│   └── bash.py            — category = "write"
└── tui/
    ├── app.py             — 新增消费 AgentEvent 的方法（替代当前 begin_streaming/stream_delta/finish_streaming 的直接耦合）
    └── render.py          — 新增 agent_progress 状态行渲染
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| Agent 与 TUI 通信方式 | `AsyncIterator[AgentEvent]` | 保持与当前 Provider 流式模式一致的编程模型；无需引入额外的事件总线依赖；TUI 按序消费事件即可 |
| 当前 `StreamEvent` 处理 | 保留在 Provider 层，不废除 | Provider 层仍需统一的流式事件结构；`StreamingCollector` 作为适配层将其转为 `AgentEvent`；Provider 接口不变 |
| 多工具并发模型 | `asyncio.gather` 读类 + `for await` 写类 | 简单直接，无需引入线程池；文件 I/O 和 glob/grep 子进程天然适合 asyncio 子进程 |
| Tool 安全分类 | Tool 基类增加 `category` 属性 | 简单直接；新工具只需声明 category 即可被正确调度；免去维护外部分类映射表 |
| Plan Mode 实现 | chat.py 层筛选工具列表 | 不侵入 Agent Loop 内部；筛选逻辑简单（一个列表推导）；Agent Loop 不感知 Plan Mode 的存在 |
| 停止条件组织 | 独立的 `StopChecker` 类 | 每种停止条件可独立测试；新增条件只需加一个方法；检查逻辑不散落在循环中 |
| Esc 取消实现 | `asyncio.CancelledError` 或标志位 | 在 Agent Loop 中检查取消标志；不硬杀正在执行的工具（工具必须跑完或超时） |
| 流式收集器 | 独立类 `StreamingCollector` | 当前 chat.py 中的 `full_response` 和 tool_call 解析逻辑内联在循环里；抽取为独立类后可单独测试，也方便后续扩展 |

### spec 覆盖检查

| F 需求 | 对应模块 |
|--------|---------|
| F1 Agent Loop (ReAct) | `agent/loop.py` |
| F2 停止条件 | `agent/stop.py` |
| F3 异步事件流 | `agent/events.py` |
| F4 流式收集器 | `agent/collector.py` |
| F5 多工具安全分批 | `agent/executor.py` |
| F6 Plan Mode | `chat.py` 编排层 |
| F7 工具结果回灌 | `agent/loop.py` + Provider 结果格式化 |
| F8 Agent 模块 | `agent/` 全部 |
