# 设计：内容包工作台与输出适配器

## 1. 两种生产族

### 完整叙事族

适用于小说、长篇短剧、复杂连续剧。继续使用现有 `CreativeProject` 内容模型：大纲、章节计划、细纲、正文/脚本、分镜、角色与连续性事实。`production_profile` 只控制推荐阶段，不改变权威内容和确认规则。

### 内容包族

适用于绘本/漫画、科普图文、公众号、小红书轮播、短视频口播、广告变体和单镜头。核心对象是可编辑的 `content_package`，而不是完整故事大纲。

```text
用户主题/素材/链接
  -> 一次内容包规划
  -> 内容卡 / 页面卡 / 镜头卡 / 文章包
  -> 图片提示词与可选视觉参数
  -> 批量图片或视频任务
  -> Asset Hub
  -> 一个或多个输出适配器
```

## 2. 内容包契约

首期复用 `ProjectContent(content_type=content_package)` 保存版本化 JSON；独立工作台可先创建无项目的 package draft，确认绑定项目后再写入项目内容。不要新建第二套 Asset 模型。

```json
{
  "package_type": "knowledge_cards",
  "title": "十二生肖",
  "topic": "用儿童友好的方式介绍十二生肖",
  "brief": "一段可直接用于导语或封面的总介绍",
  "audience": "可选",
  "style": "中国剪纸绘本",
  "aspect_ratio": "4:3",
  "items": [
    {
      "index": 1,
      "title": "鼠",
      "text": "页面介绍或卡片正文",
      "fact": "可核验的事实表述（科普卡可选）",
      "source": "来源名称或说明（科普卡可选）",
      "source_url": "公开来源链接（没有链接时为空字符串）",
      "image_prompt": "可直接提交给图片模型的提示词",
      "video_prompt": "可选动作提示词",
      "source_refs": [],
      "asset_ids": [],
      "status": "draft"
    }
  ],
  "outputs": [],
  "source_context": {},
  "version": 1
}
```

`items` 是最小可重跑单元。用户可以只重生成第 3 页或第 5 张卡，不重新生成整个主题。每个 item 的图片/视频任务、Asset Hub 资产和提示词都保留 provenance。

## 3. 首批 package_type

| 类型 | 必填输入 | 一次规划输出 | 默认媒体 |
| --- | --- | --- | --- |
| `page_book` | 主题 | 页数、页标题、页面文字、图片提示词 | 图片 |
| `knowledge_cards` | 主题 | 总介绍、知识卡、图片提示词、事实来源占位 | 图片 |
| `article_package` | 主题/素材/链接 | 标题候选、导语、正文段落、封面和配图提示词、HTML/Markdown | 图片/文档 |
| `social_carousel` | 主题/产品/观点 | 标题、6-10 张卡片、正文、标签、图片提示词 | 图片 |
| `shot_list` | 一句话创意/参考图 | 时长、镜头卡、首帧提示词、动作提示词、口播/字幕 | 图片/视频 |
| `single_media` | 一句话或参考资产 | 一个图片/视频规划摘要 | 图片/视频 |

`storybook` 可以映射为 `page_book`；`knowledge_content` 映射为 `knowledge_cards`；`platform_note` 不再直接进入小说式 outline，而是默认创建 `article_package` 或 `social_carousel`，由用户选择目标输出适配器。

### 3.1 Profile 字段与入口分流

现有 profile 保留原有 `id`、`label`、`project_type` 和兼容用的阶段列表，新增以下声明式字段：

```json
{
  "production_family": "narrative | content_package",
  "package_type": "page_book",
  "required_inputs": ["topic"],
  "optional_inputs": ["reference_assets", "source_links", "style", "audience"],
  "planning_unit": "package | item",
  "output_adapters": ["pdf_ebook", "asset_bundle"]
}
```

分流规则固定在创建项目和独立工作台入口：

- `production_family=narrative` 进入现有 `/story`，继续显示大纲、圣经、章节、正文/脚本、分镜和 Writer Room。
- `production_family=content_package` 进入内容包工作台；创建表单只显示该 profile 的 `required_inputs` 和可选输入，不渲染完整叙事字段。
- 旧项目没有 `production_family` 时，按 `production_profile` 映射；未知或缺失 profile 继续按现有短剧默认值处理，避免历史项目打不开。
- `storybook` 的默认新建行为改为 `page_book`；需要复杂连续恐怖漫画时显式选择“连续叙事”或 `vertical_drama`，而不是让轻量故事默认承受完整设定门禁。

建议的初始映射：

| profile | production_family | package_type | planning_unit |
| --- | --- | --- | --- |
| `novel_serial` | `narrative` | - | `stage` |
| `vertical_drama` | `narrative` | - | `stage` |
| `storybook` | `content_package` | `page_book` | `item` |
| `knowledge_content` | `content_package` | `knowledge_cards` | `item` |
| `platform_note` | `content_package` | `article_package` | `package` |
| `single_shot` | `content_package` | `single_media` | `item` |

## 4. 多平台能力拆分

从 `backend/app/services/ai/outline_service.py` 提取可复用的 `ContentPackagePlanner`，从 `MultiPlatformGen.tsx` 提取主题、模板选择、批量任务和结果回流逻辑，保留现有接口兼容层：

- `POST /api/v1/images/generate-outline`：继续支持旧的多平台生图请求，内部转换为 `content_package`。
- `POST /api/v1/images/generate-batch`：继续支持旧批量请求，增加可选 `package_id/item_ids`。
- 新增内容包 API 时复用同一个 planner、`PlatformTemplate` 和生成服务，不复制供应商调用。
- 独立 `/multi-platform-gen` 仍可直接使用，生成结果可保存为内容包或 Asset Hub 资产。
- `/story` 的内容包项目调用共享服务，不跳转到独立页面再重新填写主题。

平台适配器只负责包装同一内容包：

- `wechat_official_account`：富文本 HTML、标题、摘要、封面、正文配图、草稿 payload。
- `xiaohongshu_carousel`：卡片尺寸、页序、标题、正文、标签。
- `douyin_short_video`：竖屏镜头、字幕/口播、视频参数。
- `pdf_ebook`：页序、图片、文字和导出文件。
- `asset_bundle`：原始 JSON、Markdown、图片和提示词清单。

适配器输出保存为 `content_package.outputs[]`，不复制或覆盖 `items`。

## 5. 数据生命周期与 API 草案

### 5.1 项目绑定与独立草稿

- 项目内内容包：以 `ProjectContent(project_id, content_type="content_package")` 保存当前版本，完整 JSON 放在 `data_json`，`title` 保存可检索标题，`text_content` 仅用于需要全文检索的文章正文。
- 独立草稿：使用稳定 `draft_id`，但不伪造 `CreativeProject`；一期实现前必须在“现有 draft service”与轻量 `content_package_drafts` 表之间做出明确选择。用户点击“绑定到项目”时创建或选择 `CreativeProject`，再写入第一条 `ProjectContent` 版本；不能把无项目内容塞入 `ProjectContent.project_id`。
- 绑定后，草稿不再作为第二份事实源；后续编辑只写项目内容版本，draft 记录保留 `bound_project_id` 和迁移时间用于审计。

### 5.2 最小 API 形状

以下是一期实现的稳定业务契约，具体路径可放在 `/api/v1/content-packages`，不复用带有平台历史语义的 `/images` 响应作为新 UI 的事实源：

| Method | Path | 用途 |
| --- | --- | --- |
| `POST` | `/api/v1/content-packages/plan` | 根据 profile、主题/素材/链接生成内容包草案 |
| `GET` | `/api/v1/content-packages/{package_id}` | 读取当前包及版本信息 |
| `PATCH` | `/api/v1/content-packages/{package_id}` | 修改主题、包级设置或指定 item |
| `POST` | `/api/v1/content-packages/{package_id}/items/{item_id}/retry` | 只重跑一个 item 的文本/提示词规划 |
| `POST` | `/api/v1/content-packages/{package_id}/media` | 对选中的 item 一次确认后提交图片/视频任务 |
| `POST` | `/api/v1/content-packages/{package_id}/outputs/preview` | 生成平台适配预览，不写外部平台 |
| `POST` | `/api/v1/content-packages/{package_id}/bind-project` | 将独立草稿绑定到项目 |

请求必须携带 `profile_id` 或 `package_type` 二选一、`source_context`（可为空）和幂等 `client_request_id`。响应统一返回 `package_id`、`version`、`items[]`、`outputs[]`、`warnings[]`，不返回隐藏推理。媒体提交的每个任务额外带 `package_id`、`item_id`、`package_version`、`source_type`、`source_index` 和 `source_title`，以便任务中心、事件日志和 Asset Hub 回溯。

### 5.3 版本、状态与血缘

- 包级版本递增；编辑一个 item 生成新包版本，并将未改 item 以引用方式保留，不复制媒体文件。
- item 状态至少包括 `draft`、`ready`、`generating`、`succeeded`、`failed`、`stale`、`archived`。
- item 的提示词或文字变化只使该 item 及明确依赖的 adapter output 变为 `stale`；已成功且无依赖变化的其他 item 保持可用。
- 输出记录包含 `source_package_id`、`source_package_version`、`source_item_ids`、`adapter_type` 和 `status`；输出失败可独立重建，不修改源包。
- 生成资产通过既有 `derived_from`、项目素材关联和任务上下文字段记录来源，禁止只在前端 state 中保存关联。

## 6. 前端工作台

内容包项目默认进入轻量工作台，而不是完整 `/story` 蓝图 Tab：

1. 顶部：主题、内容类型、风格、页数/卡数、画幅和目标平台。
2. 中部：内容包摘要和可编辑 item 列表。
3. 每个 item：文字、图片提示词、参考资产、生成图片/视频、状态和重试。
4. 批量栏：一次确认后批量提交选中的 item，结果进入任务中心和 Asset Hub。
5. 输出栏：选择公众号/小红书/PDF/素材包等适配器，预览后导出或进入发布草稿。

完整叙事项目仍进入当前大纲/圣经/章节工作台；可从完整项目派生内容包，但派生包是新版本/新输出，不改变正文事实。

## 7. 一次生成与确认边界

- 主题规划、内容卡和提示词生成属于文本规划，可一次完成；失败可局部重试。
- 图片/视频批量生成是消耗型操作，提交前一次确认即可，不要求每张重复确认。
- 外部发布、下载、覆盖或删除继续遵循现有确认机制。
- 内容包规划只保存用户可见的摘要和提示词，不保存隐藏思维链。
