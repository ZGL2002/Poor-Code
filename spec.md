# PoorCode Spec

## 背景
从零构建一个命令行 AI 编码助手。当前项目目录为空，仅有 README.md。
用户需要先在终端中获得一个可用的多轮对话界面，后续迭代再加入 agent 能力。

## 目标
- 提供命令行交互式对话界面（TUI），用户输入问题后流式输出 AI 回复
- 支持 Anthropic 和 OpenAI 两种 LLM 后端协议，通过 YAML 配置文件切换
- Provider 层抽象为统一接口，方便后续扩展新后端
- 首次迭代范围严格限定为纯对话，不含 tool use、文件操作、代码编辑

## 功能需求
- F1: 配置文件管理
  - 用户首次启动时，自动生成默认配置文件 `~/.poorcode/config.yaml`
  - 配置文件包含四个字段：`protocol`、`model`、`base_url`、`api_key`
  - 程序启动时读取配置，配置缺失或格式错误时给出明确提示

- F2: Provider 抽象层
  - 定义统一的 LLM Provider 接口，对外暴露 `chat(messages, stream=True)` 方法
  - 输入为标准化的消息列表（system/user/assistant 角色），输出为流式文本增量
  - 根据配置中的 `protocol` 字段自动选择对应实现

- F3: Anthropic 协议支持
  - 实现 Anthropic Messages API 调用（`/v1/messages`）
  - 支持 SSE 流式响应解析，逐 token 产出文本增量
  - 支持 extended thinking（在请求中开启，流式响应中识别 thinking delta 并处理）

- F4: OpenAI 协议支持
  - 实现 OpenAI Chat Completions API 调用（`/v1/chat/completions`）
  - 支持 SSE 流式响应解析，逐 token 产出文本增量

- F5: 交互式对话界面
  - 终端启动后进入对话循环，显示欢迎信息
  - 支持多轮对话，AI 能记住上下文历史
  - 输入 `/exit` 或 `/quit` 退出，`Ctrl+C` 也退出

- F6: 多轮上下文
  - 单次会话内维护完整对话历史（用户与助手消息交替追加）
  - 每一轮新请求都携带此前全部上下文，实现连续多轮对话
  - 程序退出后历史不保留

- F7: 终端界面布局
  - 启动后呈现全功能终端界面，自上而下包含：
    (a) 启动横幅：ASCII 猫咪图案 + 应用名与版本号 + 当前工作目录
    (b) 一行就绪提示信息
    (c) 对话区：依时间顺序展示历次用户输入与助手回复
    (d) 底部带边框的输入框，含 ❯ 提示符与占位文字（如 "Send a message..."）
    (e) 底部状态栏：左侧显示活动 provider 名称，右侧显示其模型名

- F8: 流式呈现与渲染
  - 助手回复在流式期间以纯文本逐字实时显示
  - 该轮回复结束后，将其整段以 Markdown 形式重新渲染美化（代码块、列表、强调等）后定型展示

- F9: 输入与提交
  - 用户在输入框键入文本，可用 Alt+Enter 插入换行进行多行编辑
  - 按 Enter 提交，提交后清空输入框，界面进入等待/流式状态
  - 流式期间不接受新的提交，直至本轮回复结束

## 非功能需求
- N1: 可扩展性
  - 新增 LLM 后端只需实现一个 Provider 子类，无需修改现有代码
  - 配置文件中 `protocol` 字段的值与 Provider 实现之间通过注册机制关联

- N2: 健壮性
  - 网络错误、API 认证失败、配置格式错误等异常情况给出可读的中文错误提示
  - 流式传输中断时，提示用户而非崩溃
  - `Ctrl+C` 在任何阶段都能安全退出

- N3: 兼容性
  - 支持 Python 3.11+（基于当前环境 3.13.9）
  - 在标准终端模拟器（iTerm2、Terminal.app、Windows Terminal、VS Code Terminal）中布局正常
  - 兼容 Anthropic Messages API 及所有提供该兼容接口的后端（如 DeepSeek）

- N4: 性能
  - 首个流式 token 在 500ms 内开始显示（在网络正常的前提下）
  - 流式渲染不产生明显的闪烁或卡顿

## 不做的事
- Tool use / function calling（本次不实现，留给后续迭代）
- 文件读写、代码编辑（本次不实现）
- MCP 协议支持（本次不实现）
- 对话历史的持久化存储（会话退出即丢弃）
- 多会话管理（每次启动只有一次会话）
- 自动补全、语法高亮等高级输入功能（本次不实现）
- 配置文件热重载（启动时读取一次）
- 用户级和项目级配置的合并（只有 `~/.poorcode/config.yaml` 一个配置源）

## 验收标准
- AC1: 首次启动时自动生成 `~/.poorcode/config.yaml`，含四个字段及默认占位值
- AC2: 手动将 `api_key` 设为无效值后启动，程序给出可读的认证错误提示
- AC3: 分别用 `protocol: anthropic` 和 `protocol: openai` 两种配置各完成一轮对话，流式输出正常
- AC4: 用支持 extended thinking 的 Anthropic 模型对话，thinking 内容不出现在最终回复中（或合理展示）
- AC5: 一次会话中连续对话 5 轮，每轮 AI 回复均携带之前上下文（通过提问验证记忆）
- AC6: 终端界面呈现启动横幅（ASCII 猫 + 名称版本 + 工作目录）、对话区、输入框、状态栏四个区域，布局完整
- AC7: 流式回复逐字显示；回复结束后渲染为美化 Markdown（含代码块语法高亮）
- AC8: Alt+Enter 可输入多行，Enter 单独提交；流式期间 Enter 不响应
- AC9: 输入 `/quit` 或按 `Ctrl+C`，程序正常退出，无异常堆栈
- AC10: 连续 20 轮对话无明显卡顿或内存持续增长
