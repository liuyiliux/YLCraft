# 核心数据模型

本目录收录**任务账本与日志**、**写作风格档案**相关模型（YLCraft 的完整数据模型见
`docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` §4）。

## 文件

| 文件 | 内容 |
|---|---|
| `概览与实体关系（summary）.md` | 任务账本五张表的分工、字段含义、可重放参数位置 |
| `写作风格档案（writing-style-model）.md` | 风格档案与项目绑定两张表的字段语义与边界（来源：`creative-writing-style-profiles`） |
| `Agent 运行数据模型（agent-run-model）.md` | Agent 运行域四张表/实体的字段**可得性**与关联缺口（哪些看似有、实际取不到） |
| `世界构建数据模型（world-building-model）.md` | 世界构建域 5 张表的字段语义，重点是来源/启用状态如何影响"AI 能看到什么、能改什么" |
| `创作项目动态状态（dynamic-state-model）.md` | `ProjectStateEntry` 台账的字段语义、折叠/去重/回滚设计与"该落这里还是角色表"的边界 |
| `叙事运行时（narrative-runtime-model）.md` | 叙事快照/事件/伏笔/风格测量四张表的字段与溯源，以及"谁能进生成上下文"的正典 vs 提案分界 |

## 加载建议

处理"任务/事件/重试/可观测性"相关需求时读取；判断某个状态或参数该落哪张表时必读。
处理"写作风格/风格绑定/T6 注入"相关需求时，读 `写作风格档案（writing-style-model）.md`。
