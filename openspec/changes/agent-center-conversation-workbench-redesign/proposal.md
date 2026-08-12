# Agent Center 对话工作台重构

## Why

当前 `/agent` 同时展示智能体说明、运行指标、对话列表、Profile、消息、完整轨迹、工具、记忆和委派配置。功能虽然可达，但主任务被管理信息淹没，辅助接口失败也缺少清晰的局部恢复入口。

YLCraft 相比直接使用 AI + Skills 的价值不是堆更多配置，而是降低普通人的操作门槛、直观呈现过程与产物，并把确定性操作交给脚本和服务以减少模型调用与 Token 消耗。

## What Changes

- 将 Agent Center 收敛为“对话列表 + 对话正文 + 输入框”的主界面。
- 智能体选择保留为紧凑上下文控件；工具、记忆、配置、完整轨迹按需打开。
- 计划、工具调用、观察、委派和确认按发生顺序内联到消息流，完成后默认折叠。
- 对线程、Profile、工具、记忆、模型和运行详情实施局部错误状态与重试，辅助能力失败不阻塞聊天。
- 增加页面级错误边界，渲染异常时保留可恢复入口。
- 将“低门槛、结果可视、脚本优先节省 Token”写入产品和架构设计约束。

## Non-goals

- 不重写 Agent 后端运行时、工具协议、记忆模型或 Supervisor/Worker 机制。
- 不删除工具测试、Profile 编辑、运行树等高级能力，只降低其默认层级。
- 不把 Agent Center 改成营销首页或数据仪表盘。

## Impact

- Frontend: `frontend/src/pages/agent/index.tsx`、Agent 专用组件与样式。
- Documentation: `docs/DESIGN.md`、`docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`、`docs/agent/agent-center.md`。
- API surface 不变。
