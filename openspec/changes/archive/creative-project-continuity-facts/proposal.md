# Creative Project Continuity Facts

## Why

YLCraft 已有 Writer Room 候选版本、主编审稿、锁定项目圣经/世界资产和服务端创作上下文包，但审稿发现的角色、时间线、地点、物件和伏笔事实仍主要停留在文本反馈中。用户需要手动重述或复制这些信息，后续章节无法可靠继承。

经过对开源小说项目的核验，长篇质量的关键不是增加一套泛化多 Agent，而是把每次写作前后的故事事实变成有来源、可确认、可追溯的状态。本变更把这一闭环落实到 YLCraft 的现有模型中。

## What Changes

- 将 Writer Room 审稿的连续性结论标准化为 `continuity_candidates`。
- 候选事实必须包含实体、断言、来源正文、严重度、建议动作和去重指纹。
- 用户可逐条确认、忽略或合并候选；确认后才写入现有 `project_bible` 或 `world_asset`，并保留来源 `ProjectContent`。
- 创作上下文包继续只注入已锁定事实；新增事实在确认前绝不作为模型硬约束。
- 在正文、润色、定向重写和 Writer Room 中显示本轮上下文摘要和事实来源，支持审计但不重复保存完整长文本。
- 增加跨章冲突检查，返回结构化结果和可执行的定向重写建议；不自动改写正文或项目事实。
- 增加段落级重写入口，优先修改用户选中的证据段落，无法精确定位时才明确提示使用整章候选重写。

## Non-goals

- 不引入第二套 Agent 会话、检查点表或向量数据库。
- 不自动接受 AI 提取的事实，不自动覆盖 `novel_body`。
- 不复制 AGPL/GPL/未声明许可证的外部实现；本变更仅采用已核验项目的产品和数据流思路。
- 不修改番茄发布流程、素材库和画布运行时。

## Reference

- `Nigh/show-me-the-story`（MIT）：章节状态机、来源化叙事记忆、伏笔状态/告警、段落级修订。
- `syrizelink/OpenFic`（Apache-2.0）：章节上下文、Agent 运行记录、检查点和工具预览的边界。
- 完整核验记录见 `docs/reference/AI_NOVEL_OPEN_SOURCE_RESEARCH.md`。

## Impact

- Backend: creative project service、Writer Room review schema、project context pack、generation logs。
- Data: extend project fact metadata or add a project-owned continuity candidate record, with Alembic migration when persistence cannot safely live in existing metadata.
- API: candidates CRUD/decision endpoints, context summary endpoint and structured conflict check endpoint.
- Frontend: `/story` Writer Room review panel, facts panel, context drawer and paragraph-rewrite controls.
- Tests/docs: service/API tests, `API_SURFACE`, architecture, creative loop guide and active OpenSpec task status.
