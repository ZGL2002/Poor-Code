# PoorCode Plan

## 架构概览

整个应用分为五层，自上而下：

```
┌─────────────────────────────────────────────┐
│                  Chat Loop                   │  编排层：启动→对话循环→退出
│              (poorcode/chat.py)              │
├─────────────────────────────────────────────┤
│                 TUI 渲染层                    │  界面层：Rich 渲染 + prompt_toolkit 输入
│    (poorcode/tui/app.py, render.py,          │
│           input_area.py)                     │
├──────────────────┬──────────────────────────┤
│   Config 模块     │     Provider 抽象层       │  业务层
│ (poorcode/config  │  (poorcode/provider/     │
│  .py)             │   base.py, registry.py)  │
│                   ├──────────┬───────────────┤
│                   │ Anthropic│   OpenAI      │
│                   │ Provider │   Provider    │
├──────────────────┴──────────┴───────────────┤
│               HTTP + SSE 传输                 │  传输层：httpx 异步 HTTP + SSE 解析
│         (poorcode/provider/http.py)          │
└─────────────────────────────────────────────┘
```

**各层职责：**

- **Chat Loop 编排层**：应用生命周期的总调度。初始化配置→创建 Provider→启动 TUI→进入对话循环（读输入→调 Provider→流式渲染→追加历史→循环）。
- **TUI 渲染层**：负责所有终端显示和用户输入。用 Rich 库渲染启动横幅、对话消息、Markdown 美化、状态栏；用 prompt_toolkit 实现底部输入框（支持 Alt+Enter 多行）。
- **Provider 抽象层**：定义 LLMProvider 统一接口。通过注册表将配置中的 `protocol` 值映射到具体实现。新增后端只需注册一个子类。
- **Provider 实现层**：AnthropicProvider 和 OpenAIProvider，各自负责消息格式转换、请求构造、SSE 事件解析。
- **传输层**：封装 httpx 异步 HTTP 客户端，统一处理连接、超时、SSE 流读取。

## 核心数据结构

### Message
标准化的对话消息，与协议无关。

| 字段 | 类型 | 说明 |
|------|------|------|
| role | str | `"system"`、`"user"`、`"assistant"` |
| content | str | 消息正文 |

### ProviderConfig
从 YAML 解析出的配置对象。

| 字段 | 类型 | 说明 |
|------|------|------|
| protocol | str | `"anthropic"` 或 `"openai"` |
| model | str | 模型名，如 `"deepseek-v4-pro"` |
| base_url | str | API 地址 |
| api_key | str | 认证密钥 |

### LLMProvider（抽象基类）

```
class LLMProvider(ABC):
    def __init__(self, config: ProviderConfig): ...

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        stream: bool = True,
    ) -> AsyncIterator[str]:
        """发送消息，返回流式文本增量迭代器。"""
        ...
```

- `messages`：历史对话列表
- `system_prompt`：可选的系统提示，与 Anthropic 的 system 参数对应
- `stream`：保留非流式路径但本次迭代仅用流式
- 返回 `AsyncIterator[str]`，每次 yield 一段增量文本（通常是一个 token）

### StreamEvent
流式响应中的统一事件结构，用于 TUI 渲染层判断内容类型。

| 字段 | 类型 | 说明 |
|------|------|------|
| type | str | `"text_delta"`、`"thinking_delta"`、`"done"` |
| content | str | 增量文本内容 |

Provider 的 `chat()` 方法内部解析 SSE 事件流，对外产出 `StreamEvent`，TUI 层据此决定显示方式（thinking 内容可折叠或单独展示）。

## 模块设计

### 模块 A: Config (`poorcode/config.py`)

**职责：** 读取、校验、生成 YAML 配置文件  
**对外接口：**
- `load_config() -> ProviderConfig` — 读取 `~/.poorcode/config.yaml`，校验字段完整性，返回配置对象
- `create_default_config(path: Path)` — 生成含占位值的默认配置文件

**依赖：** 无外部模块依赖（仅 PyYAML）  
**对应需求：** F1

### 模块 B: HTTP 传输 (`poorcode/provider/http.py`)

**职责：** 封装 httpx 异步 HTTP 客户端，统一处理 SSE 流读取  
**对外接口：**
- `async post_sse(url, headers, json_body) -> AsyncIterator[dict]` — 发送 POST 请求，逐行读取 SSE 事件，yield 解析后的 JSON dict

**依赖：** httpx  
**对应需求：** F3, F4（为两个 Provider 提供统一的 SSE 读取能力）

### 模块 C: Provider 注册表 (`poorcode/provider/registry.py`)

**职责：** 维护 protocol 名到 Provider 类的映射，提供工厂方法  
**对外接口：**
- `register_provider(protocol: str, provider_cls)` — 注册一个 Provider 实现
- `create_provider(config: ProviderConfig) -> LLMProvider` — 根据配置创建对应的 Provider 实例

**依赖：** `poorcode/provider/base.py`  
**对应需求：** F2, N1

### 模块 D: Anthropic Provider (`poorcode/provider/anthropic.py`)

**职责：** 实现 Anthropic Messages API 调用  
**对外接口：** 实现 `LLMProvider.chat()`

**关键逻辑：**
- 将 `list[Message]` 转换为 Anthropic Messages API 的 `messages` 数组格式
- 将 `system_prompt` 放入 Anthropic 专用的 `system` 参数
- 请求体中设置 `anthropic-beta: thinking-*` header 开启 extended thinking（如配置的模型支持）
- 解析 SSE 事件流：`content_block_delta` → `text_delta` / `thinking_delta`；`message_stop` → `done`

**依赖：** `poorcode/provider/base.py`、`http.py`  
**对应需求：** F3

### 模块 E: OpenAI Provider (`poorcode/provider/openai.py`)

**职责：** 实现 OpenAI Chat Completions API 调用  
**对外接口：** 实现 `LLMProvider.chat()`

**关键逻辑：**
- 将 `list[Message]` 转换为 OpenAI 的 `messages` 数组（含 `system` 角色的消息）
- SSE 事件解析：`choices[0].delta.content` → `text_delta`；`[DONE]` → `done`

**依赖：** `poorcode/provider/base.py`、`http.py`  
**对应需求：** F4

### 模块 F: TUI 渲染 (`poorcode/tui/render.py`)

**职责：** 用 Rich 库渲染所有终端输出  
**对外接口：**
- `render_welcome(console, version, cwd)` — 渲染启动横幅（ASCII 猫 + 应用名版本 + 工作目录）、就绪提示、状态栏
- `render_user_message(console, text)` — 渲染用户消息
- `render_streaming(console, text_delta)` — 追加流式文本到当前输出区
- `render_final(console, full_text)` — 流式结束后将整段用 Rich Markdown 重新渲染
- `render_status_bar(console, provider_name, model_name)` — 刷新底部状态栏

**依赖：** rich  
**对应需求：** F7, F8

### 模块 G: TUI 输入 (`poorcode/tui/input_area.py`)

**职责：** 用 prompt_toolkit 实现底部输入框  
**对外接口：**
- `create_input_area() -> PromptSession` — 创建并返回配置好的输入会话对象
- `async get_input(session) -> str` — 异步获取用户输入，支持 Alt+Enter 多行、Enter 提交

**依赖：** prompt_toolkit  
**对应需求：** F9

### 模块 H: TUI 应用 (`poorcode/tui/app.py`)

**职责：** 组合渲染和输入，管理 TUI 生命周期  
**对外接口：**
- `class TuiApp` — 持有 Console、输入会话、Provider 信息
- `tui.start()` — 显示欢迎界面
- `tui.show_user_message(text)` — 显示用户输入
- `tui.begin_streaming()` — 进入流式等待状态（禁用输入）
- `tui.stream_delta(delta)` — 流式追加文本
- `tui.finish_streaming(full_text)` — 流式结束，Markdown 渲染，恢复输入
- `tui.show_error(message)` — 显示错误信息

**依赖：** `render.py`、`input_area.py`  
**对应需求：** F5, F7, F8, F9

### 模块 I: Chat Loop (`poorcode/chat.py`)

**职责：** 应用主循环，编排配置→Provider→TUI→对话  
**对外接口：**
- `async run()` — 应用入口：加载配置、创建 Provider、初始化 TUI、进入对话循环

**流程：**
1. `load_config()` → 校验
2. `create_provider(config)` → 获取 Provider 实例
3. `tui.start()` → 显示横幅和状态栏
4. 循环：
   - `tui.get_input()` → 读取用户输入
   - 检查 `/quit`、`/exit`、空输入
   - 追加 `Message(role="user", content=...)` 到历史
   - `tui.begin_streaming()`
   - `provider.chat(messages=history, stream=True)` → 异步迭代 StreamEvent
   - 对每个 `text_delta`：`tui.stream_delta(delta.content)`
   - 对每个 `thinking_delta`：视配置决定展示或隐藏
   - 收到 `done`：`tui.finish_streaming(full_text)`
   - 追加 `Message(role="assistant", content=full_text)` 到历史
5. 捕获 `KeyboardInterrupt` → 安全退出

**依赖：** `config.py`、`provider/`、`tui/`  
**对应需求：** F5, F6

## 模块交互

一次对话请求的完整调用链：

```
用户按 Enter 提交
    │
    ▼
chat.py (Chat Loop)
    │
    ├─ tui.input_area.get_input()          ← 读取用户输入
    ├─ tui.app.begin_streaming()           ← 通知 TUI 进入等待状态（禁用输入）
    │
    ├─ provider.chat(messages=history)     ← 调用 LLMProvider 接口（流式）
    │       │
    │       ├─ 消息格式转换（Message → API 格式）
    │       ├─ http.post_sse(url, headers, body)  ← 发送 POST，SSE 流读取
    │       │       │
    │       │       └─ httpx.AsyncClient.stream()  ← 异步 HTTP 流
    │       │
    │       └─ SSE 事件解析 → yield StreamEvent     ← 协议层解析
    │
    ├─ 对每个 StreamEvent:
    │     ├─ text_delta      → tui.app.stream_delta(content)   ← 逐字追加
    │     ├─ thinking_delta  → (缓存或展示)
    │     └─ done            → tui.app.finish_streaming(full)  ← Markdown 重渲染
    │
    ├─ 追加 assistant Message 到 history
    └─ tui.input_area.get_input()          ← 等待下一轮输入
```

**数据流方向：**
- `config.yaml` → `ProviderConfig` → `LLMProvider.__init__()` （启动时，单向）
- `list[Message]` ⇄ `chat()` / TUI （对话中，循环追加）
- `StreamEvent` → TUI 渲染 （流式期间，单向推送）

## 文件组织

```
Poor Code/
├── poorcode/
│   ├── __init__.py
│   ├── __main__.py              — 入口：python -m poorcode
│   ├── chat.py                  — Chat Loop 编排
│   ├── config.py                — 配置读取、校验、默认生成
│   ├── provider/
│   │   ├── __init__.py          — 导出 + 启动时注册所有 Provider
│   │   ├── base.py              — LLMProvider 抽象基类、Message、StreamEvent
│   │   ├── registry.py          — Provider 注册表 + create_provider 工厂
│   │   ├── anthropic.py         — AnthropicProvider
│   │   ├── openai.py            — OpenAIProvider
│   │   └── http.py              — httpx SSE 请求封装
│   └── tui/
│       ├── __init__.py
│       ├── app.py               — TuiApp 类，TUI 生命周期管理
│       ├── render.py            — Rich 渲染（横幅、消息、Markdown、状态栏）
│       └── input_area.py        — prompt_toolkit 输入框
├── spec.md                       — [已完成] Spec
├── plan.md                       — [当前] Plan
├── task.md                       — [下一步] Tasks
├── checklist.md                  — [下一步] Checklist
├── pyproject.toml                — 项目元数据与依赖
└── README.md
```

依赖声明 (`pyproject.toml`)：
- `httpx` — 异步 HTTP + SSE 流
- `rich` — Markdown 渲染与美化
- `prompt_toolkit` — 输入框（Alt+Enter 多行）
- `pyyaml` — YAML 配置解析

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 异步框架 | `asyncio` + `httpx` | Python 内置异步能力，httpx 是唯一同时支持 HTTP/2 和 SSE 流式读取的主流客户端。不引入 aiohttp 等额外异步框架 |
| SSE 解析 | 自行实现行级解析 | SSE 协议极其简单（`event:` + `data:` 行），百行以内即可完成，不必引入 sseclient 等第三方库 |
| Provider 注册机制 | `dict` 映射 + 装饰器注册 | 每种协议一行 `register_provider("anthropic", AnthropicProvider)` 即可加入。新增后端只需写一个新文件 + 一行注册，满足 N1 可扩展性 |
| extended thinking 处理 | 流式期间缓存，不回显；回复结束后可选折叠展示 | Anthropic 的 thinking delta 是内部推理，不应混入正式回复。缓存后可供调试，但不影响 Markdown 渲染 |
| 消息模型 | 自建 `Message` 命名元组，含 `role` 和 `content` | 避免依赖任何 SDK 的数据模型。两种协议共用同一消息格式，在 Provider 内部各自转换 |
| 配置位置 | `~/.poorcode/config.yaml` | 遵循 XDG 惯例，用户主目录下独立目录。与项目文件隔离，避免误提交密钥 |
| 启动命令 | `python -m poorcode` | 标准 Python 包启动方式，无需安装脚本。后续可通过 pyproject.toml 的 scripts 字段注册为 `poorcode` 命令 |
| 依赖版本策略 | 不锁定 patch 版本 | pyproject.toml 中声明 `>=` 约束，确保兼容性同时允许 bug 修复更新 |
| 错误处理 | 分层处理，TUI 层统一展示 | HTTP 错误、SSE 解析错误、配置错误在各层捕获并转为中文提示，由 TuiApp.show_error() 统一渲染 |

### spec 覆盖检查

| F 需求 | 对应模块 |
|--------|---------|
| F1 配置文件管理 | Config (`config.py`) |
| F2 Provider 抽象层 | Provider 基类 (`provider/base.py`) + 注册表 (`provider/registry.py`) |
| F3 Anthropic 协议 | AnthropicProvider (`provider/anthropic.py`) + HTTP (`provider/http.py`) |
| F4 OpenAI 协议 | OpenAIProvider (`provider/openai.py`) + HTTP (`provider/http.py`) |
| F5 交互式对话界面 | Chat Loop (`chat.py`) + TuiApp (`tui/app.py`) |
| F6 多轮上下文 | Chat Loop (`chat.py`) 维护 `list[Message]` |
| F7 终端界面布局 | TUI 渲染 (`tui/render.py`) + 输入 (`tui/input_area.py`) |
| F8 流式呈现与渲染 | TuiApp 流式方法 (`tui/app.py`) + Rich Markdown (`tui/render.py`) |
| F9 输入与提交 | 输入框 (`tui/input_area.py`) |
