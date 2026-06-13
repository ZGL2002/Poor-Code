# PoorCode Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性

- [ ] C1: 所有 15 个文件已创建（验证：`find poorcode -name '*.py' | wc -l` 输出 14；`ls pyproject.toml` 存在）
- [ ] C2: `python -m poorcode` 可正常启动，无 import 错误（验证：启动后显示欢迎界面，无 traceback）
- [ ] C3: 默认配置文件自动生成（验证：删除 `~/.poorcode/config.yaml` 后首次启动，自动生成含四个字段的默认文件）
- [ ] C4: 配置缺失字段时给出明确提示（验证：手动删除 yaml 中 `api_key` 字段后启动，程序以中文提示具体缺失字段并退出）
- [ ] C5: 无效 `api_key` 给出认证错误（验证：填入假密钥，启动后发送消息，程序以中文提示认证失败，不崩溃）
- [ ] C6: `protocol: anthropic` 下可正常对话（验证：配置 DeepSeek 或真实 Anthropic 端点，启动对话，流式输出正常）
- [ ] C7: `protocol: openai` 下可正常对话（验证：配置 OpenAI 端点，启动对话，流式输出正常）
- [ ] C8: Extended thinking 不混入回复（验证：用支持 thinking 的 Anthropic 模型对话，终版 Markdown 渲染中不含思考内容，或合理折叠展示）

## 集成

- [ ] C9: Provider 注册表可扩展（验证：在 `__init__.py` 中注册新协议名，`create_provider()` 能正确实例化）
- [ ] C10: Chat Loop 正确调用 TUI 生命周期（验证：启动后首次输入，依次进入 begin_streaming → stream_delta × N → finish_streaming → 恢复输入）
- [ ] C11: HTTP 层正确处理 SSE 流（验证：对话过程中，网络断开时程序提示「连接中断」而非崩溃）

## 编译与测试

- [ ] C12: 项目可正常安装（验证：`pip install -e .` 无错误）
- [ ] C13: `poorcode` 命令可用（验证：`which poorcode` 或 `python -m poorcode --help` 可执行）
- [ ] C14: Python 语法无错误（验证：`python -m compileall poorcode/` 全部通过）

## 端到端场景

- [ ] C15: 场景 1 — 首次用户体验
  - 操作：安装依赖 → 启动 `python -m poorcode` → 自动生成默认配置 → 提示用户编辑配置 → 用户填入真实密钥 → 再次启动 → 看到 ASCII 猫横幅和状态栏 → 输入「你好，请用中文回复」→ 观察逐字流式输出 → 回复结束后看到美化 Markdown → 继续输入「还记得我刚才说的话吗？」→ AI 回答中引用前文 → 输入 `/quit` → 程序正常退出
  - 预期结果：全程无报错，流式输出平滑，上下文记忆正确

- [ ] C16: 场景 2 — 错误处理
  - 操作：删除 `~/.poorcode/config.yaml` → 启动程序 → 看到配置生成提示 → 不改配置直接再启动 → 看到「请填写配置」提示 → 填入无效 api_key → 启动后输入问题 → 看到中文认证错误提示 → 程序未崩溃，可继续操作（或退出）
  - 预期结果：所有错误路径有中文提示，无 traceback 泄漏

- [ ] C17: 场景 3 — 多行输入与流式阻断
  - 操作：启动后输入多行文本（用 Alt+Enter 换行）→ Enter 提交 → 流式回复期间按 Enter → 不响应新输入 → 流式结束后 Enter 恢复可用 → 输入 `/exit` 退出
  - 预期结果：多行输入正确提交，流式期间输入被阻断，结束后恢复

- [ ] C18: 场景 4 — 20 轮连续对话
  - 操作：启动后连续输入 20 轮问题（可用简单问题如「说一个数：1」「说一个数：2」……）→ 观察输出 → `/quit` 退出
  - 预期结果：20 轮无卡顿，内存无明显增长，每轮回复均能引用之前对话内容
