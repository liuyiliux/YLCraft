# 核心数据模型

本目录收录**任务账本与日志**、**写作风格档案**相关模型（YLCraft 的完整数据模型见
`docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` §4）。

## 文件

| 文件 | 内容 |
|---|---|
| `概览与实体关系（summary）.md` | 任务账本五张表的分工、字段含义、可重放参数位置 |
| `写作风格档案（writing-style-model）.md` | 风格档案与项目绑定两张表的字段语义与边界（来源：`creative-writing-style-profiles`） |

## 加载建议

处理"任务/事件/重试/可观测性"相关需求时读取；判断某个状态或参数该落哪张表时必读。
处理"写作风格/风格绑定/T6 注入"相关需求时，读 `写作风格档案（writing-style-model）.md`。
