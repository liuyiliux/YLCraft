# Design: 创作项目工作台 UI 重构

## Design Direction

采用 redesign-existing-projects 的结构审计方法和 design-taste-frontend 的高 agency 交互原则：先收敛层级、密度和状态，再做视觉细节。目标是让用户在 3 秒内回答“我在哪个项目、当前处于哪个阶段、下一步该做什么”。

视觉基线：低噪声深色工作台、单一青绿色行动色、清晰的中性层级、紧凑但不拥挤的控件；不使用紫蓝渐变、无意义光晕、堆叠卡片和常驻右侧大面板。

## Information Architecture

项目总览：项目状态与下一步 -> 故事蓝图（大纲） -> 项目圣经（世界/文风/规则） -> 章节规划（全书） -> 角色与参考资产 -> 生产进度与待处理问题 -> 最近活动。

单章工作室：章节导航 -> 章节契约/细纲 -> 正文与 Writer Room -> 脚本/分镜/素材 -> 上下文与连续性检查 -> 本章生成、审核和版本操作。

信息按用途而不是按后端表拆分：方向层（大纲、圣经、角色、章节规划）属于总览；制作层（细纲、正文、脚本、分镜、生成结果）属于单章；证据层（连续性、伏笔、trace、版本、来源素材）只在需要时浮现。项目总览是决策面，完整大纲或圣经只在用户展开对应 section 后出现。

## Entry and Resumption

 - 首次进入没有大纲的项目，主操作为“建立故事蓝图”；已有章节时，主操作为“继续第 N 章 · 当前阶段”。
 - “继续上次工作”恢复持久化的 mode、chapter、stage 和编辑焦点；对应内容无效时回退到总览下一步建议。
 - 总览中的章节规划是生产队列，不是正文预览。行内只显示编号、标题、目标、阶段、阻塞原因和最近活动；点击才进入单章。
 - 从总览进入章节时，打开该章节最需要完成的阶段，而不是永远进入第一个 tab。

## Layout

- Shared header 只保留项目名、工作模式、章节、保存状态、模型入口和主操作。不要平铺所有模型和按钮。
- 模型是项目运行设置，不是每次创作决策。默认只显示当前模型摘要；只有切换模型或生成时展开选择器。
- 总览使用一个主内容区。大纲、圣经、章节规划、角色和资产是可折叠 sections，默认只展开相关的一块。
- 单章工作室才显示可收窄章节导航；总览不显示章节正文列表。
- 右侧 inspector 默认关闭，仅在检查上下文、连续性、伏笔或素材时打开；关闭后主区自然扩展。
- 单章主区采用阶段 tabs：细纲、正文、脚本、分镜、审核。每个阶段一个主编辑面和一个主动作。
- 总览 sections 和单章 tabs 是不同层级：前者回答“全书是否能继续”，后者回答“本章现在做哪一步”。未生成的后续阶段显示明确依赖，而不是空白大面板。
- 高级 JSON、批量生成、导出和危险操作进入更多菜单或抽屉。
- 桌面目标：章节导航 240-280px，主编辑区 720-960px，inspector 320-380px；移动端单列。

## Interaction Rules

- 项目级动作写“编辑项目设定/更新章节规划”，章节级动作写“生成本章细纲/生成正文”。
- 任意时刻只有一个视觉主按钮；次要动作使用文字按钮、菜单或图标按钮并提供 tooltip。
- 普通编辑优先 inline edit、折叠区和 inspector；只有删除、发布或覆盖锁定内容使用确认框。
- 生成按钮显示目标、依赖和状态；缺少上游时在按钮附近说明缺什么。
- 保存状态显示未保存、保存中、已保存、保存失败。切换项目或章节不得丢失本地编辑。
- 章节状态使用少量稳定语义：未开始、待生成、草稿、待审核、已确认、受阻；不要让用户理解每个后端内容类型。
- URL 或 metadata 恢复项目、模式、章节和阶段，刷新不隐式新建数据。

## Decision Ledger and Continuity Visibility

- Project overview contains a decision ledger rather than a generic progress dashboard. Each item exposes current chapter, blocking dependency, next irreversible action, and the factual evidence used to derive it.
- A next-step recommendation is advisory only. The user can accept, defer, or reject it; the chosen disposition is recorded as UI preference/activity evidence and never silently dispatches generation, promotion, locking, publishing, or cost-incurring work.
- Continuity is not inspector-only. The active prose and storyboard stages show a compact, persistent summary of unresolved fact conflicts, overdue setups, missing references, or review blockers. It links to detailed evidence and actions in ContextInspector.
- On narrow screens the continuity summary remains in the main stage header, while ContextInspector becomes an explicit pull-up/drawer. Approval-relevant facts must not disappear merely because the side panel is unavailable.

## Components

ProjectWorkspaceShell、ProjectOverview、ProjectStageSummary、ResumeWorkspace、ChapterProductionQueue、ChapterNavigator、ChapterStudio、ContextInspector、GenerationTrace。
ResumeWorkspace 恢复上次工作和下一步建议；ChapterProductionQueue 是总览章节生产队列。建议逻辑只读取现有 outline、chapter plan、ProjectContent、生成日志、锁定和审核状态，不能持久化第二份阶段事实。

这些组件只负责展示和交互编排，继续调用现有 creative-project API 和服务，不复制业务规则。

## Acceptance Principles

- 新用户无需文档即可区分项目总览和单章写作。
- 进入已有项目后，用户能一次点击继续上次工作；没有上次工作时能看到下一步原因和正确入口。
- 总览只显示决策所需的摘要与展开入口，不能退化为全部字段的折叠长表单。
- 总览首屏不出现全书正文；章节详情必须通过单章工作室进入。
- 展开一个总览模块不会同时展开其他模块。
- 1440px 下正文、章节导航和 inspector 不互相挤压；关闭 inspector 后主区扩展。
- 现有生成、保存、锁定、审核、版本、导出动作仍可到达。
- 刷新后项目、模式、章节和阶段恢复；键盘焦点、加载、空、错误和禁用状态完整。
