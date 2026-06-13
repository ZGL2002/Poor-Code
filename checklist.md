# 工具系统 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性

- [ ] C1: 所有 16 个文件已创建或修改（验证：`find poorcode -name '*.py' | wc -l` 输出 ≥20；`ls poorcode/tools/` 含 10 个文件）
- [ ] C2: 六个工具全部注册（验证：`python -c "from poorcode.tools import list_tools; print([t.name for t in list_tools()])"` 输出 `['read', 'write', 'edit', 'bash', 'glob', 'grep']`）
- [ ] C3: Tool 抽象基类可正常导入（验证：`python -c "from poorcode.tools.base import Tool, ToolResult, ToolContext"` 无报错）
- [ ] C4: Provider 基类支持 tools 参数（验证：`python -c "from poorcode.provider.base import LLMProvider, ProviderConfig; c=ProviderConfig('anthropic','m','url','key'); p=LLMProvider(c, tools=[])"` 无报错）
- [ ] C5: ToolCallRequest 可导入（验证：`python -c "from poorcode.provider.base import ToolCallRequest"` 无报错）

## 工具功能验证

- [ ] C6: Read 工具读取文件（验证：`python -c "import asyncio; from poorcode.tools.read import ReadTool; from poorcode.tools.base import ToolContext; from pathlib import Path; r=asyncio.run(ReadTool().execute({'file_path':'README.md'}, ToolContext(Path.cwd(),30))); print(r.success, r.content[:100])"` → success=True，输出 README 内容）
- [ ] C7: Read 工具文件不存在（验证：同上但 file_path='__nonexistent__' → success=False, error='not_found'）
- [ ] C8: Write 工具创建文件（验证：执行写入 → 检查文件存在 → 内容一致 → 清理测试文件）
- [ ] C9: Edit 工具精确替换（验证：创建临时文件含 'hello' → edit(old='hello', new='world') → 检查文件内容变为 'world' → 清理）
- [ ] C10: Edit 工具多处匹配报错（验证：文件含两行 'hello' → edit(old='hello') → success=False, error='not_unique'）
- [ ] C11: Edit 工具未找到报错（验证：文件不含 'xyz' → edit(old='xyz') → success=False, error='not_found'）
- [ ] C12: Bash 工具执行命令（验证：`command='echo hello'` → success=True, stdout 含 'hello'）
- [ ] C13: Bash 工具超时（验证：`command='sleep 120'` + timeout=2 → success=False, error='timeout'）
- [ ] C14: Glob 工具匹配文件（验证：`pattern='**/*.py'` → 返回 .py 文件列表）
- [ ] C15: Grep 工具搜索代码（验证：`pattern='import'` → 返回各行含 import 的文件、行号、内容）
- [ ] C16: 路径越界被拒绝（验证：Read file_path='/etc/passwd' → success=False, 提示路径越界）
- [ ] C17: 工具结果截断（验证：创建 >100KB 文件 → Read 读取 → content 末尾含 '...(内容已截断, 超过 100KB)'）

## 集成验证

- [ ] C18: Provider 注册表可扩展（验证：注册新协议 → `create_provider()` 正确实例化 → 已有行为不被破坏）
- [ ] C19: 工具注册表可扩展（验证：`register(MyTool())` → `get('mytool')` 能找到 → `list_tools()` 含新工具）
- [ ] C20: `to_anthropic_format()` 输出正确（验证：输出为 list[dict]，每项含 name、description、input_schema 三个字段）
- [ ] C21: `to_openai_format()` 输出正确（验证：输出为 list[dict]，每项含 type='function' 和嵌套的 function 对象）
- [ ] C22: 不传工具时行为不变（验证：`provider = create_provider(config)` 不传 tools → 纯文本对话正常，无工具调用）
- [ ] C23: Provider chat() 签名未被破坏（验证：现有调用 `provider.chat(messages=history, stream=True)` 仍可用）

## 编译与测试

- [ ] C24: Python 语法无错误（验证：`python -m compileall poorcode/` 全部通过）
- [ ] C25: `python -m poorcode` 可正常启动（验证：启动后显示欢迎界面，无 import 错误或 traceback）
- [ ] C26: 项目可正常安装（验证：`pip install -e .` 无错误）

## 端到端场景

- [ ] C27: 场景 1 — 读取文件工具调用
  - 操作：配置有效 API Key → 启动 `python -m poorcode` → 输入「读一下 README.md」→ 观察终端显示「🔧 read … ⏳ 执行中」→ 等待→ 显示「🔧 read … ✅ 完成」→ 模型基于文件内容生成文本回复 → 输入「/quit」
  - 预期：工具调用状态行正确显示，模型回复引用 README.md 内容

- [ ] C28: 场景 2 — 编辑文件工具调用
  - 操作：启动 → 输入「把 README.md 中的所有 PoorCode 替换为 RichCode」→ 模型调用 edit 工具 → 终端显示「🔧 edit … ✅ 完成」→ 输入「读一下 README.md 验证」→ 模型调用 read → 回复确认替换生效 → 手动还原文件
  - 预期：Edit 成功执行，Read 验证内容已改

- [ ] C29: 场景 3 — 文件不存在时的错误恢复
  - 操作：启动 → 输入「读一下 notexist.txt」→ 模型调用 read → 终端显示「🔧 read … ❌ not_found」→ 模型在回复中说明文件不存在 → 程序不崩溃
  - 预期：工具失败不崩溃，模型基于错误信息给出合理回复

- [ ] C30: 场景 4 — 执行命令工具调用
  - 操作：启动 → 输入「用 ls -la 列出当前目录」→ 终端显示「🔧 bash … ✅ 完成」→ 模型列出目录内容
  - 预期：Bash 工具正确执行，结果在模型回复中呈现

- [ ] C31: 场景 5 — 搜索代码工具调用
  - 操作：启动 → 输入「搜索项目中的所有 Python 文件」→ 模型调用 glob → 终端显示「🔧 glob … ✅ 完成」→ 模型列出 .py 文件 → 输入「搜索所有 import 语句」→ 模型调用 grep → 模型汇总搜索结果
  - 预期：Glob 和 Grep 正常工作，结果准确

- [ ] C32: 场景 6 — 多工具被拒绝
  - 操作：启动 → 输入「同时读一下 README.md 和 chat.py」→ 若模型尝试调用多个工具 → 终端显示错误（「模型请求了 2 个工具…」或模型只调了 1 个且说明原因）→ 程序不崩溃
  - 预期：多工具场景下程序正确处理，不崩溃

- [ ] C33: 场景 7 — 路径越界被拒绝
  - 操作：启动 → 输入「读 /etc/passwd」→ 模型调用 read → 终端显示「🔧 read … ❌」或「路径越界」→ 模型回复说明无法访问 → 程序不崩溃
  - 预期：安全限制生效

- [ ] C34: 场景 8 — 不配置工具时纯文本对话
  - 操作：修改 `chat.py` 不传 tools（模拟关闭）→ 启动 → 输入「你好」→ 流式回复正常 → 多次对话 → 上下文记忆正常
  - 预期：纯文本对话行为与当前版本完全一致

- [ ] C35: 场景 9 — API 认证失败时工具调用
  - 操作：填写无效 api_key → 启动 → 输入「读一下 README.md」→ 程序给出中文认证错误提示 → 不崩溃
  - 预期：认证错误不影响工具系统的健壮性

- [ ] C36: 场景 10 — 20 轮混合对话
  - 操作：启动 → 交替进行纯文本对话和工具调用（读文件、执行命令、搜索代码）→ 总计 20 轮 → 输入「/quit」
  - 预期：全程无卡顿，无内存持续增长，每轮上下文正确
