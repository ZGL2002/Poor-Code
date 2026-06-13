# Agent Loop Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性

- [ ] C1: Agent 包全部 5 个模块文件存在（验证：`ls poorcode/agent/` 输出 `__init__.py events.py collector.py executor.py stop.py loop.py`）
- [ ] C2: Tool 基类含 `category` 属性（验证：`python -c "from poorcode.tools.base import Tool; print(hasattr(Tool, 'category'))"` 输出 `True`）
- [ ] C3: 六个工具 category 正确分类（验证：`python -c "from poorcode.tools import list_tools; cats = {t.name: t.category for t in list_tools()}; print(cats)"` 输出 3 个 read + 3 个 write）
- [ ] C4: 配置 `max_iterations` 可读取（验证：`python -c "from poorcode.config import load_config; print(load_config().max_iterations)"` 输出 `25`）
- [ ] C5: AgentEvent 全部类型可导入（验证：`python -c "from poorcode.agent import AgentLoop, AgentProgressEvent, AgentDoneEvent, TextDeltaEvent, ToolCallEvent, ToolResultEvent, TokenUsageEvent, ErrorEvent"` 无报错）

## 工具执行器

- [ ] C6: 读类并发执行（验证：创建两个 Read call → execute_all → 两个 tool_result 事件产出且耗时约等于单次 Read）
- [ ] C7: 写类串行执行（验证：创建两个 Write call → execute_all → 第一个完成后第二个才开始）
- [ ] C8: 混合分批（验证：创建一个 Read + 一个 Write → execute_all → Read 先完成，Write 后完成）
- [ ] C9: 未注册工具返回错误结果（验证：ToolCallRequest(tool_name="nonexistent") → execute_all → 产出 ToolResultEvent(success=False)）

## 停止条件

- [ ] C10: 自然停止（验证：Agent Loop 收到无工具调用的 LLM 响应 → 产出 AgentDoneEvent(reason="natural_stop")）
- [ ] C11: 迭代上限（验证：max_iterations=2，发需要多轮工具的任务 → 第 2 轮后产出 AgentDoneEvent(reason="max_iterations")）
- [ ] C12: 连续未知工具（验证：连续 3 次调用未注册工具 → 产出 AgentDoneEvent(reason="consecutive_unknown_tools")）
- [ ] C13: 流错误停止（验证：模拟 Provider 抛异常 → 产出 AgentDoneEvent(reason="stream_error")）

## 事件流

- [ ] C14: text_delta 实时转发（验证：流式接收期间，text_delta 事件逐个产出，不等待流结束）
- [ ] C15: 流式结束后 tool_calls 完整（验证：collector 的 tool_calls 列表包含本次所有工具调用）
- [ ] C16: agent_progress 每轮产出（验证：Agent Loop 每轮开始产出 AgentProgressEvent，含正确 iteration）
- [ ] C17: token_usage 每轮产出（验证：LLM 调用结束后 TokenUsageEvent 被产出）
- [ ] C18: agent_done 结束信号（验证：Agent Loop 退出前最后一个事件是 AgentDoneEvent）

## Plan Mode

- [ ] C19: /plan 切换模式（验证：输入 /plan → 终端提示切换到 Plan Mode）
- [ ] C20: Plan Mode 限制工具（验证：/plan 后，传给 Provider 的 tools 仅含 Read/Glob/Grep）
- [ ] C21: /do 切换回全工具（验证：/do 后，传给 Provider 的 tools 恢复全部六个）
- [ ] C22: 命令不影响对话历史（验证：/plan 和 /do 不追加到 history）

## 编译与测试

- [ ] C23: Python 语法无错误（验证：`python -m compileall poorcode/` 全部通过）
- [ ] C24: `python -m poorcode` 可正常启动（验证：启动后显示欢迎界面，无 import 错误或 traceback）
- [ ] C25: 项目可正常安装（验证：`pip install -e .` 无错误）

## 端到端场景

- [ ] C26: 场景 1 — 单轮工具自主完成
  - 操作：配置有效 API Key → 启动 → 输入「读一下 README.md」→ 不输入任何其他内容
  - 预期：终端显示工具调用状态（🔧 read … ✅ 完成）→ 模型基于文件内容生成回复 → Agent Loop 自动停止 → 等待下一轮输入

- [ ] C27: 场景 2 — 多轮工具自主推进
  - 操作：启动 → 输入「先找到所有 .py 文件，再搜索其中包含 import 的行」
  - 预期：Glob 执行 → Grep 执行 → 模型汇总结果 → 全过程无需用户催促

- [ ] C28: 场景 3 — 迭代上限兜底
  - 操作：修改 config.yaml 中 max_iterations=2 → 启动 → 输入复杂任务（需要多次工具调用）
  - 预期：Agent Loop 在 2 轮后停止 → 终端显示「达到迭代上限」

- [ ] C29: 场景 4 — 纯文本对话（0 轮工具）
  - 操作：启动 → 输入「你好」→ 模型回复
  - 预期：无工具调用 → Agent Loop 立即停止 → 流式回复正常

- [ ] C30: 场景 5 — 模型基于错误自行纠错
  - 操作：启动 → 输入「读一下 notexist.txt」
  - 预期：Read 返回错误 → 模型可能尝试 Glob 搜索相似文件名 → 不再盲目重试同一路径

- [ ] C31: 场景 6 — 多工具并发读
  - 操作：启动 → 输入「同时读 README.md 和 CLAUDE.md」
  - 预期：两个 Read 并发执行 → 两个结果都返回 → 模型回复

- [ ] C32: 场景 7 — Plan Mode 调研 + 执行
  - 操作：启动 → 输入 /plan → 输入「我想修改 README.md 的标题，先帮我看看项目结构」→ 模型只能读/搜索 → 输入 /do → 输入「现在改标题」→ 模型可 Edit
  - 预期：Plan 阶段无写操作，Do 阶段可用全部工具

- [ ] C33: 场景 8 — Esc 取消 Agent Loop
  - 操作：启动 → 输入触发 Agent Loop 的任务 → 执行中按 Esc
  - 预期：当前轮次停止 → 回到输入等待状态 → 对话历史保留

- [ ] C34: 场景 9 — 连续工具调用不崩溃
  - 操作：启动 → 进行 5+ 轮工具调用的复杂任务
  - 预期：全程无崩溃 → 每轮进度可见 → 最终完成或达到上限

- [ ] C35: 场景 10 — 不配置工具时兼容
  - 操作：修改 chat.py 不传 tools → 启动 → 输入「你好」
  - 预期：流式回复正常 → 无 Agent Loop 相关错误 → 多轮对话正常

- [ ] C36: 场景 11 — 进度和 Token 可见
  - 操作：启动 → 输入触发工具调用的任务
  - 预期：终端可见「🔄 第 1/25 轮」等进度信息 → 结束后可见 Token 用量或停止原因摘要
