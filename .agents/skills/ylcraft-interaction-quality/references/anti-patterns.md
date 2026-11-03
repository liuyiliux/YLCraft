# 反模式（真实案例，别重犯）

从 SKILL.md 拆出，2026-11-03。

> 这是明细 / 查询表，按需 grep，不要整篇读。

## 反模式（真实案例，别重犯）

### 我们自己的（2026-10-14 实测）

| 症状 | 位置 |
| --- | --- |
| 生图预览显示 `返回字段：success、normalized_request、visual_plan、` | `agent/index.tsx` `summarizeToolResult` |
| 步骤输出直接 `JSON.stringify(step.output, null, 2)` | 同文件 L2557-2561 |
| 失败时用户看到 `badly formed hexadecimal UUID string [SQL: SELECT asset_nodes.id AS…]` | 实测截图 |
| 同页面两个「确认执行」按钮 | 实测 |
| 待确认横幅疑似执行了**旧对话**的待确认项 | 实测 |

### 别人的（行业教训）

| 症状 | 出处 | 用户原话 |
| --- | --- | --- |
| 改版后功能"找不到" | Google Flow | 「**drag and drop from where? where are the assets?**」 |
| 东西更多了但更乱 | Google Flow | 「Yes things are **more easily accessible** but it just **feels cluttered**」 |
| 心智模型说不清 | Google Flow | 「**no entiendo la lógica**」 |
| 功能被埋 | Google Flow | 「just **buried in a different spot**」 |
| 模块化过度暴露 | ComfyUI #6635 | 「GUI Should Simplify, Not Complicate」 |
| 参数写了不生效 | LINUX DO | 「我让其生成 16:9，最终得到的比例是 1672×941」 |

> **注意：Google Flow 那批用户骂的不是"丑"，是"找不到"和"不懂逻辑"。**
> 所以**改视觉解决不了功能不能用**。

---

