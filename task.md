# PoorCode Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `pyproject.toml` | 项目元数据与依赖声明 |
| 新建 | `poorcode/__init__.py` | 包初始化 |
| 新建 | `poorcode/__main__.py` | 入口：`python -m poorcode` |
| 新建 | `poorcode/config.py` | 配置读取、校验、默认生成 |
| 新建 | `poorcode/chat.py` | Chat Loop 编排 |
| 新建 | `poorcode/provider/__init__.py` | 导出 + 启动时注册所有 Provider |
| 新建 | `poorcode/provider/base.py` | LLMProvider、Message、StreamEvent |
| 新建 | `poorcode/provider/registry.py` | Provider 注册表 + 工厂函数 |
| 新建 | `poorcode/provider/http.py` | httpx SSE 请求封装 |
| 新建 | `poorcode/provider/anthropic.py` | AnthropicProvider |
| 新建 | `poorcode/provider/openai.py` | OpenAIProvider |
| 新建 | `poorcode/tui/__init__.py` | TUI 包初始化 |
| 新建 | `poorcode/tui/render.py` | Rich 渲染（横幅、消息、Markdown、状态栏） |
| 新建 | `poorcode/tui/input_area.py` | prompt_toolkit 输入框 |
| 新建 | `poorcode/tui/app.py` | TuiApp 生命周期管理 |

## T1: 项目骨架搭建

**文件：** `pyproject.toml`、`poorcode/__init__.py`  
**依赖：** 无  
**步骤：**
1. 创建 `pyproject.toml`，声明 `[project]` 元数据（name=poorcode, requires-python=">=3.11"）
2. 声明依赖：httpx, rich, prompt_toolkit, pyyaml（均用 `>=` 约束）
3. 配置 `[project.scripts]`：`poorcode = "poorcode.__main__:main"`
4. 创建 `poorcode/__init__.py`，写入版本号 `__version__ = "0.1.0"`

**验证：** `python -c "import poorcode; print(poorcode.__version__)"` 输出 `0.1.0`

## T2: 核心数据结构定义

**文件：** `poorcode/provider/base.py`  
**依赖：** T1  
**步骤：**
1. 定义 `Message` 数据类（`role: str`、`content: str`）
2. 定义 `StreamEvent` 数据类（`type: str`、`content: str`），type 取值为 `"text_delta"`、`"thinking_delta"`、`"done"`
3. 定义 `LLMProvider` 抽象基类，含 `__init__(self, config)` 和异步抽象方法 `chat(self, messages, system_prompt=None, stream=True) -> AsyncIterator[StreamEvent]`

**验证：** `python -c "from poorcode.provider.base import Message, StreamEvent, LLMProvider"` 无报错

## T3: 配置模块

**文件：** `poorcode/config.py`  
**依赖：** T1  
**步骤：**
1. 定义 `ProviderConfig` 数据类（`protocol: str`、`model: str`、`base_url: str`、`api_key: str`）
2. 实现 `create_default_config(path: Path)`——在 `~/.poorcode/` 目录下生成 `config.yaml`，含四个字段及占位值，目录不存在则先创建
3. 实现 `load_config() -> ProviderConfig`——读取 `~/.poorcode/config.yaml`，校验四个字段是否存在且非空，缺失或为空时给出明确的中文错误提示并退出
4. 文件不存在时自动调用 `create_default_config()`，生成后提示用户填入真实值并退出

**验证：** 删除 `~/.poorcode/config.yaml`（如存在），运行 `python -c "from poorcode.config import load_config; ..."`，观察默认配置生成和提示

## T4: HTTP SSE 传输层

**文件：** `poorcode/provider/http.py`  
**依赖：** T1  
**步骤：**
1. 实现 `async post_sse(url: str, headers: dict, json_body: dict) -> AsyncIterator[dict]`
2. 内部使用 `httpx.AsyncClient` 发送流式 POST 请求
3. 逐行读取响应体，按 SSE 协议解析 `event:` 和 `data:` 行
4. 对每个事件 yield 解析后的 JSON dict
5. 处理连接超时（默认 60 秒）和读取异常，转为中文异常信息

**验证：** 无需独立验证，将在 T6/T7 中通过 Provider 间接验证

## T5: Provider 注册表

**文件：** `poorcode/provider/registry.py`  
**依赖：** T2  
**步骤：**
1. 维护模块级 `_registry: dict[str, type[LLMProvider]]` 字典
2. 实现 `register_provider(protocol: str, provider_cls: type[LLMProvider])`
3. 实现 `create_provider(config: ProviderConfig) -> LLMProvider`，查找 `_registry` 中匹配 `protocol` 的类并实例化，找不到则抛出含中文提示的 `ValueError`

**验证：** `python -c "from poorcode.provider.registry import _registry, register_provider; ..."` 确认注册和查找逻辑

## T6: Anthropic Provider

**文件：** `poorcode/provider/anthropic.py`  
**依赖：** T2, T4  
**步骤：**
1. 实现 `AnthropicProvider(LLMProvider)`，构造时保存 `ProviderConfig`
2. 实现 `_build_messages(history: list[Message]) -> list[dict]`——将 `Message` 列表转为 Anthropic Messages 格式（role/content 映射）
3. 实现 `_build_body(messages, system_prompt)`——构造请求体，含 `model`、`messages`、`system`（如提供）、`stream: true`、`max_tokens: 4096`
4. 若需 extended thinking，构造时添加 `thinking` 参数和 `anthropic-beta` header
5. 实现 `chat()`——调用 `post_sse()`，解析 SSE 事件：
   - `content_block_start` → 识别 block 类型
   - `content_block_delta`（`text_delta`） → yield `StreamEvent("text_delta", text)`
   - `content_block_delta`（`thinking_delta`） → yield `StreamEvent("thinking_delta", text)`
   - `message_stop` → yield `StreamEvent("done", "")`
6. 处理 Anthropic 错误事件（`error` 类型），抛出含错误信息的中文异常

**验证：** 暂不独立运行，待 T8 注册后通过 T13 chat loop 整体验证

## T7: OpenAI Provider

**文件：** `poorcode/provider/openai.py`  
**依赖：** T2, T4  
**步骤：**
1. 实现 `OpenAIProvider(LLMProvider)`，构造时保存 `ProviderConfig`
2. 实现 `_build_messages(history: list[Message]) -> list[dict]`——将 `Message` 列表转为 OpenAI Chat Completions 格式
3. 实现 `_build_body(messages, system_prompt)`——构造请求体，含 `model`、`messages`、`stream: true`；system_prompt 作为 `role: "system"` 的消息插入 messages 开头
4. 实现 `chat()`——调用 `post_sse()`，解析 SSE 事件：
   - `choices[0].delta.content` 存在 → yield `StreamEvent("text_delta", content)`
   - `[DONE]` → yield `StreamEvent("done", "")`

**验证：** 暂不独立运行，待 T8 注册后通过 T13 chat loop 整体验证

## T8: Provider 包初始化与注册

**文件：** `poorcode/provider/__init__.py`  
**依赖：** T5, T6, T7  
**步骤：**
1. 从各子模块导入 `LLMProvider`、`Message`、`StreamEvent`、`registry` 函数
2. 在模块加载时调用 `register_provider("anthropic", AnthropicProvider)` 和 `register_provider("openai", OpenAIProvider)`
3. 确保外部只需 `from poorcode.provider import ...` 即可使用全部导出

**验证：** `python -c "from poorcode.provider import create_provider, registry; print(registry._registry.keys())"` 输出含 `anthropic` 和 `openai`

## T9: TUI 渲染模块

**文件：** `poorcode/tui/render.py`  
**依赖：** T1（仅依赖 rich）  
**步骤：**
1. 实现 `render_welcome(console: Console, version: str, cwd: str, provider_name: str, model_name: str)`
   - 打印 ASCII 猫咪图案（约 8-10 行的猫图案）
   - 打印应用名 PoorCode + 版本号
   - 打印当前工作目录
   - 打印一行就绪提示信息
2. 实现 `render_user_message(console: Console, text: str)`——以用户标签展示输入内容
3. 实现 `begin_streaming(console: Console)`——显示一个占位的空输出区，准备接收流式文本
4. 实现 `stream_delta(console: Console, delta: str)`——在同一行/区域追加增量文本（使用 `Live` context 或直接 print 无换行）
5. 实现 `finish_streaming(console: Console, full_text: str)`——清除流式输出区，用 `Markdown` 渲染完整回复（含代码块语法高亮）
6. 实现 `render_status_bar(console: Console, provider_name: str, model_name: str)`——在底部渲染一行状态栏（左：provider 名，右：模型名）
7. 实现 `render_error(console: Console, message: str)`——以红色高亮显示错误信息

**验证：** 编写临时脚本手动调用各函数，观察终端输出布局是否符合预期

## T10: TUI 输入模块

**文件：** `poorcode/tui/input_area.py`  
**依赖：** T1（仅依赖 prompt_toolkit）  
**步骤：**
1. 实现 `create_input_session() -> PromptSession`——创建 `PromptSession`，配置：
   - 提示符 `❯ `（用 Rich 样式或纯文本）
   - 底部工具栏/占位文字 "Send a message... (Alt+Enter 换行, Enter 发送)"
   - 启用 `multiline=True`，但 Enter 提交（通过自定义 key_bindings）
2. 实现自定义 `KeyBindings`：
   - `Enter` → 提交当前输入（`validate_while_typing=False`）
   - `Alt+Enter`（或 `Escape, Enter`） → 插入换行
3. 实现 `async get_input(session: PromptSession) -> str`——异步获取用户输入文本

**验证：** 编写临时脚本启动输入框，测试 Enter 提交和 Alt+Enter 换行

## T11: TUI 应用管理

**文件：** `poorcode/tui/app.py`  
**依赖：** T9, T10  
**步骤：**
1. 实现 `TuiApp` 类：
   - `__init__(self, provider_name, model_name, version, cwd)` → 创建 `Console` 实例、输入 `PromptSession`
   - `start()` → 调用 `render_welcome()` + `render_status_bar()`
   - `show_user_message(text)` → 调用 `render_user_message()`
   - `begin_streaming()` → 设置流式状态标志
   - `stream_delta(delta)` → 调用 `stream_delta()`
   - `finish_streaming(full_text)` → 调用 `finish_streaming()` + 重置标志
   - `show_error(message)` → 调用 `render_error()`
   - `get_input()` → 调用 `get_input(session)`
   - `is_streaming` 属性 → 返回当前是否在流式接收中

**验证：** `python -c "from poorcode.tui.app import TuiApp; ..."` 能成功实例化

## T12: TUI 包初始化

**文件：** `poorcode/tui/__init__.py`  
**依赖：** T11  
**步骤：**
1. 从 `app.py` 导出 `TuiApp`
2. 确保外部只需 `from poorcode.tui import TuiApp`

**验证：** `python -c "from poorcode.tui import TuiApp"` 无报错

## T13: Chat Loop 编排

**文件：** `poorcode/chat.py`  
**依赖：** T3, T8, T12  
**步骤：**
1. 实现 `async run()` 异步函数：
   - 调用 `load_config()` 获取 `ProviderConfig`
   - 调用 `create_provider(config)` 获取 Provider 实例
   - 计算版本号和工作目录
   - 创建 `TuiApp(config.protocol, config.model, version, cwd)`
   - 调用 `tui.start()`
   - 初始化 `history: list[Message] = []`
2. 进入对话循环：
   - `user_input = await tui.get_input()`
   - `user_input.strip()` 为空则跳过，继续下一轮
   - 匹配 `/quit` 或 `/exit`（忽略大小写）→ break 退出
   - 追加 `Message(role="user", content=user_input)` 到 history
   - `tui.begin_streaming()`
   - `full_response = ""`
   - `async for event in provider.chat(messages=history, stream=True):`
     - `event.type == "text_delta"` → `full_response += event.content`；`tui.stream_delta(event.content)`
     - `event.type == "thinking_delta"` → 缓存（暂不展示）
     - `event.type == "done"` → `tui.finish_streaming(full_response)`；break
   - 追加 `Message(role="assistant", content=full_response)` 到 history
3. 捕获 `KeyboardInterrupt` → `tui.show_error("已退出")`；返回 0
4. 捕获网络/API 异常 → `tui.show_error(中文消息)`；不崩溃，继续循环

**验证：** 暂不独立运行（需真实 API 配置），待 T14 完成入口后整体验证

## T14: 程序入口

**文件：** `poorcode/__main__.py`  
**依赖：** T13  
**步骤：**
1. 实现 `main()` 函数——调用 `asyncio.run(run())`
2. 处理 `KeyboardInterrupt` 优雅退出

**验证：** 配置有效 API Key 后运行 `python -m poorcode`，能启动、显示欢迎界面、进行一次对话、`Ctrl+C` 退出

## 执行顺序

```
T1 (项目骨架)
 │
 ├── T2 (数据结构) ──┬── T5 (注册表) ──┐
 │                   │                  │
 ├── T3 (配置)       ├── T6 (Anthropic) ├── T8 (Provider 包) ──┐
 │                   │                  │                       │
 └── T4 (HTTP SSE) ──┴── T7 (OpenAI) ──┘                       │
                                                                │
 T9 (渲染) ──┬── T11 (TuiApp) ── T12 (TUI 包) ─────────────────┤
             │                                                   │
 T10 (输入) ─┘                                                   │
                                                                 │
 T3 ────────────────────────────────────────────────────────────┤
                                                                 │
 T8 + T12 ─────────────────── T13 (Chat Loop) ── T14 (入口) ────┘
```

- T2、T3、T4 在 T1 完成后可并行
- T6 和 T7 在 T2/T4 完成后可并行
- T9 和 T10 可并行（互不依赖）
