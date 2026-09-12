# Tasks

## Phase 1: 生产方案协议

- [x] 1. 定义 `ContentProductionProfile`、阶段节点、可选阶段、输出适配器和约束字段。
- [x] 2. 为短剧、故事漫画/童话绘本、科普内容、平台图文、小说、单镜头实验建立内置 profile。
- [x] 3. 创建项目时选择内容目标，保留独立能力入口，不强制正文阶段。
- [x] 4. 将现有多平台生图和图片编辑器标记为通用输出/后处理能力。

## Phase 2: 导演 Agent 编排

- [x] 5. 将导演计划建模为可编辑的结构化 plan，并关联 project/canvas/assets。
- [x] 6. 为故事、脚本、视觉、角色、分镜、图片、视频、平台适配、审稿建立 Skill 能力声明。
- [x] 7. 用 `TeamComposer` 编排导演与 specialist Skills，保留每个角色独立 Run 和汇合 observation。
- [x] 8. 增加“只重跑受影响节点”的依赖分析与版本回流。
- [x] 9. 在对话中展示计划摘要、输入资产、提示词、模型参数、产物和确认点。

## Phase 3: 图像/视频思考式生产

- [x] 10. 生成前输出可审计的视觉规划摘要，不暴露隐藏思维链。
- [x] 11. 支持对话式局部修改：角色、风格、构图、比例、镜头动作、页码和平台版式。
- [x] 12. 生成结果自动进入任务中心、事件日志和 Asset Hub 血缘。

## Phase 4: AI 来源标记与文件元数据清理

- [x] 13. 评估并锁定 `guillaumemeyer/watermarks-remover` 的许可证、版本和本地服务边界。
- [x] 14. 引入 `remove-ai-marks` Skill 或等效内部适配器，支持扫描、预览、生成副本和回滚。
- [x] 15. 增加图片、视频、音频、文档的文件元数据/C2PA/EXIF/XMP 清理任务记录。
- [x] 27. 复刻 `watermarks-remover` Layer A 与文档/图片覆盖：扩展文本隐形 Unicode（bidi/标签/非字符/空间同形字）清理并保留 emoji 胶水与合法 ZWJ/ZWNJ；新增文档 xlsx/pptx/odt/epub；新增图片 gif；审计报告增加 `unicode_breakdown`。
- [x] 16. 与平台采集“获取无水印资源”和图片编辑器区分导航、文案和 API。
- [x] 17. 增加授权来源字段、原文件保护、操作日志和失败诊断。
- [x] 17b. 增加“只读检测不清理”的合成水印审计能力（CtrlRegen/SynthID）：`POST /api/v1/assets/{asset_id}/deep-watermark-detect` 只上报检测结果、绝不修改文件；内置确定性 CtrlRegen 式鲁棒性统计检测器（纯 CPU、零 GPU/ML）；SynthID 做成可选适配器，默认跳过（配置 `YLCRAFT_SYNTHID_DETECT_ENABLED`/`PROVIDER` 才启用），避免把 GPU/ML 变成硬依赖；结果写入平台事件日志。
- [x] 17c. 在 Writer Room 新增可选 `prose_watermark_clean` 步骤：对最终正文做统计型文本水印（Layer B）的最大努力改写扰动（同义替换/句法重组/连接词变换/句边界调整），保持事实与 90%-110% 篇幅，作为独立候选不自动提升、不进默认批量链；Agent 与前端均以显式步骤形式暴露（前端「可选」标签），配套后端单测验证可生成并提升为 `novel_body`。
- [x] 17d. 新增显性可见水印去除（图片/视频）与视频合成水印检测：`POST /api/v1/assets/{asset_id}/watermark-remove` 接收 `method`（delogo/blur/crop）与 `region`（预设角落+inset 或 x/y/w/h），基于系统 ffmpeg（delogo/crop 滤镜）与 PIL（图片 blur 用 GaussianBlur）生成派生副本、原文件保留、带 `derived_from` 血缘并写平台事件日志；deep-watermark-detect 扩展支持视频（ffmpeg 抽帧统计检测并平均，返回 frame_count/per_frame_scores）；前端审计去水印页新增「显性可见水印去除」区块（选择水印位置与方法）；配套后端单测。

## Phase 5: 验证与文档

- [x] 18. 为 profile 校验、导演计划、Skill Team 汇合、局部重跑增加后端测试。
- [x] 19. 为独立生成 → 素材中枢 → 项目/画布 → 平台适配做浏览器 smoke。
  - _2026-09-13 部分完成（真实浏览器，patchright + Chromium；**未勾，缺"独立生成"这一环的实际提交**）：_
    - _独立生成（`/image-gen`）：页面渲染 HTTP 200；提示词输入框 2 个；后端/模型/尺寸三个选择器可用（硅基流动 / siliconflow-Kolors / 1024x1024）；Prompt 参考库入口存在。**只验证页面能力，未点击提交**（避免未经批准的额度消耗）。_
    - _素材中枢（`/assets`）：HTTP 200，25 个资产卡片 / 23 张图；既有资产可见（Cyberpunk 分镜图、SMOKE 验收图、角色立绘）。_
    - _项目/画布（`/canvas`、`/story`）：两页均渲染；画布含「素材库」区。_
    - _平台适配（`/multi-platform-gen`、`/platform-templates`）：两页均渲染；平台/尺寸选择器可用。_
    - _全程 **0 个 >=400 响应、0 条控制台 error**。首轮曾出现 1 条 `net::ERR_NO_BUFFER_SPACE`，单独复访 `/assets` 两次均为 0 错误，判定为 headless Chromium 的系统级 socket 缓冲噪声，非应用缺陷。_
    - _补做首环（用户已确认，消耗 1 次生图额度）：`/image-gen` 填提示词（含标记 `CPO19SMOKE`）→ 点「**开始生成**」→ **17 秒**后产物出现在 `/assets`（名字带标记）；全程 0 个 >=400、0 条控制台 error。至此链路四段全部走通，本条完成。_
    - _**一处观察（不判定为缺陷）**：任务 #12 声称"生成结果自动进入任务中心、事件日志和 Asset Hub 血缘"。实测**生图**结果：_
      - ✅ _事件日志：`platform_event_logs` 有完整记录（`scene=image`、`task_type=image_generation`、`status=success`、`provider=siliconflow-Kolors`、`duration_ms=5216`）_
      - ✅ _Asset Hub 血缘：产物 17s 内可查_
      - ⚠️ _**任务中心：查不到**_ —— `/api/v1/tasks` 聚合的是 `project_task_records`（creative_writing 61 / world_domain_expansion 5 / novel_download 1）+ `video_generation_tasks`(24) + `model3d_generation_tasks`(6)，**不含 image_generation**。_
      - _合理推测：生图是同步快操作（5.2s），视频/3D 是异步长任务，故只有后者进入任务中心。这可能是设计取舍而非缺陷；若要求三者一致，需把生图也纳入任务中心聚合（改动点：`/api/v1/tasks` 的聚合来源）。留待确认。_
    - _操作要点（供复现）：`/image-gen` 的提交按钮文案是「**开始生成**」；提示词框 placeholder 为「描述你想要生成的图像…」；反向提示词在第二个 textarea。_
- [x] 20. 更新系统架构、API Surface、Agent Skill 文档和创作项目指南。

## Phase 6: 外部 Agent API

- [x] 21. 固化外部 Agent 能力发现契约：`GET /api/v1/ai/capabilities` 返回 LLM、生图、视频、3D、语音连接器、模型、能力、尺寸和配置状态。
- [x] 22. 固化素材中枢上传契约：外部 Agent 可通过 `POST /api/v1/assets/upload` 上传图片、视频、音频、文本和 3D 文件，并获得稳定资产 ID。
- [x] 23. 固化生成与任务契约：外部 Agent 可调用图片/视频/3D/文本生成接口，通过任务详情、事件日志和素材血缘查询结果。
- [x] 24. 为项目上下文建立统一字段：`project_id`、`content_id`、`production_profile`、`source_type`、`source_index` 和 `source_title`。
- [ ] 25. 增加外部 Agent API 的鉴权、作用域、速率限制和消耗型操作确认策略；未完成前不把开发 CORS 直接视为公网安全方案。（已落地：平台级 `ExternalApiKey`（迁移 020）+ `/api/v1/external-api-keys` 管理（含 `quota` 次数配额，迁移 021）、Bearer 校验（key_hash/active/scope）+ 每 key 滑动窗口限流 + generate scope 消耗配额（quota_used 递增、超限 403）+ 强制开关 `YLCRAFT_EXTERNAL_API_REQUIRE_KEY=1`，覆盖 `/images/generate`、`/videos/generate`、`/llm/chat`、`/model-3d/generate`、`/assets/upload`、`/assets/{id}`、`/logs`、`/ai/capabilities`；待：`/tasks/{task_id}` 等剩余读接口与公开文档示例）
- [x] 26. 提供外部 Agent API 示例和 OpenAPI 使用说明，覆盖“查询模型 → 上传图片 → 生图/生视频 → 轮询任务 → 读取素材”的完整闭环。
