# 前端公共组件清单（连接器 / 模型选择）

> **这是账本，不是介绍文档。** 迁移一件就更新一件；新页面要画「供应商 + 模型」之前先读这里。
> 体量红线：**≤ 12 KB**，超了拆 `reference` 子文件。

## 为什么有这份文档

2026-09-03 的收编（`53da6a38` 抽出 `ProviderModelSelect`、`d29faae4` 收编复用 `BackendSelect`）
**只迁移了当时在改的页面**（世界地图 / 小说世界 / 视觉抽屉 / 故事圣经），并把「立绘、
story、canvas、agent 接入上述公共件」写进了**提交说明**里 —— 没有落到任何文档。

后果：

- 六周后角色详情仍是手写两套 Select，`useLlmConnectors` 只有 2 个使用者；
- 2026-10-31 Agnes Video 2.0 下线：视频页因为自己写了一份「默认选中 `available_models[0]`」，
  把已下线的模型发给供应商（`model_not_found`），排查花了一整轮对话。

⇒ 规则写进文档、迁移进度记在这里，不再依赖 commit message。

## 一、唯一规则：「连接器 → 模型」

实现在 `frontend/src/utils/modelSelection.ts`（**不要再手写第二份**）：

| 函数 | 规则 |
| --- | --- |
| `pickDefaultConnector(backends)` | 默认**连接器** = `is_default === true` 的优先，否则列表第一个 |
| `resolveModelSelection(backend)` | 默认选中 = 权威默认模型；为空才退回 `available_models[0]` |
| `resolveModelCandidates(backend)` | 下拉候选 = 默认模型 + `available_models`，去空 / 去重 / 默认模型排第一 |
| `resolveDefaultModel(backend)` | 权威默认模型：`model` 优先，其次 `default_model` |

⚠️ **默认连接器不能取 `items[0]`**（2026-11-01 事故）：
`/ai/connectors?provider_type=llm` 的列表第一个可能是没启动的本地反代
（`http://127.0.0.1:8317`），用户标记的 `is_default` 连接器排在后面。
取 `items[0]` ⇒ 角色详情「AI 补全」直接报 `All connection attempts failed`。
所有"选默认连接器"的地方都走 `pickDefaultConnector`。

⚠️ **默认模型有两个字段名，必须都认**：

- `/videos/backends`、`/images/backends` → `model`（就是连接器默认模型）
- `/ai/connectors`（LLM / 图像连接器列表）→ `default_model`

2026-10-31 迁移角色详情时踩到：只认 `model` 会让 `/ai/connectors` 的默认模型丢失、
退回 `available_models[0]` —— 又一次同类漂移。规则已在工具里兼容两种字段，页面不要再写适配层。

`available_models` 可能过期，**永远不能覆盖默认模型**。

前端 dev 沙箱里跑不了 vitest 时，逻辑测试仍要**本地**跑一次
（`npx vitest run src/pages/video-gen/modelSelection.test.ts`）。

## 二、两级下拉的语义（先确认，再画 UI）

「第一级 + 第二级」在不同页面含义不同，这是历史遗留，不要混：

| 页面 | 第一级 | 第二级 | 备注 |
| --- | --- | --- | --- |
| `ProviderModelSelect`（公共） | 连接器 | **模型** | 推荐语义 |
| 视频生成 / 我的数据 / 角色详情 | 连接器 | 模型 | 已迁移或迁移中 |
| 图片生成「高级设置」 | 厂商 `provider_label` | **连接器（部署配置）** | 标签写「模型」但实际选连接器 —— 待定，见待迁移 #2 |

新增页面一律用 **连接器 → 模型**；确实需要「厂商 → 连接器」时，先在这里登记再实现。

## 三、公共件

| 文件 | 职责 | 当前使用者 |
| --- | --- | --- |
| `components/BackendSelect.tsx` | 连接器单选（`provider_label — name` + 参考图 Tag）；`filterBackendsByCapability` 的唯一实现 | `ProviderModelSelect`、`MultiPlatformGen` |
| `components/ai/ProviderModelSelect.tsx` | 「连接器 + 模型」双下拉；切换连接器自动带默认模型；支持 `capability` 过滤、`providerOptionLabel` 自定义文案 | 世界地图、视觉抽屉、故事圣经、图片生成（LLM 优化）、角色详情（迁移中） |
| `hooks/useLlmConnectors.ts` | LLM 连接器拉取 + 默认模型（内部走 `resolveModelSelection`） | 世界地图、故事圣经、角色详情（迁移中） |
| `utils/modelSelection.ts` | 默认模型 / 候选规则（唯一实现） | 视频生成、图片生成、`MultiPlatformGen`、`ProviderModelSelect`、`useLlmConnectors` |
| `components/content-columns/index.tsx` | 内容列表列库（查询页 / 我的数据 / 点赞共用） | 查询页、我的数据、点赞面板 |
| `components/platform-detail/` | 详情抽屉 / 媒体预览 / 评论（非 B 站） | 查询页、我的数据、点赞面板 |
| `utils/download.ts` | 文本/blob 下载；`openDownloadPage()` = 新标签页打开 `/download?url=` | 4 个「去水印下载」入口 |

## 四、待迁移清单（唯一账本）

| # | 位置 | 现状 | 目标 | 优先级 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | `character-detail` 立绘 / AI 补全 | 已换成 `ProviderModelSelect` + `useLlmConnectors` | — | P1 | 已完成 2026-11-01（用户截图确认「图像供应商 / 模型」合成一行渲染） |
| 2 | 图片生成「高级设置」厂商 → 部署配置 | 手写两级，第二级其实是连接器 | 待定：保留厂商分组，内层复用连接器选择；或抽 `VendorConnectorSelect` 变体 | P2 | 待设计 |
| 3 | 图片生成「AI 优化」LLM 对 | 已换成 `ProviderModelSelect`（保留「配置名（厂商）」标签） | — | P1 | 已迁移 2026-10-31（tsc 通过；弹窗需先填提示词才能打开，未截图） |
| 4 | 视频生成 | 已用 `utils/modelSelection`；模型展示逻辑特殊（单模型时只读输入框） | 保持现状即可 | P3 | 规则已完成 2026-10-31（浏览器实测模型显示 2.5-flash） |
| 5 | `MultiPlatformGen` | 曾 `available_models[0]` 优先（列表优先） | 已改用 `resolveModelSelection` / `resolveModelCandidates` | P1 | 已完成 2026-10-31（浏览器实测 LLM 模型已带默认值） |
| 6 | `novel-world` / `WorldMapEditor` / `writing-styles` / `book-source` | 各写一份默认模型回退 | 已切到 `resolveModelSelection` | P3 | 已完成 2026-10-31（tsc 通过） |
| 7 | `agent` / `story` / `canvas` | `default_model \|\| model` 顺序正确，但各自一份；agent 还含组合逻辑 | 评估后切到 `resolveModelSelection` | P3 | 待办 |

> 全仓已无「`available_models[0]` 优先于默认模型」的写法（2026-10-31 扫描确认）。

## 五、迁移验收（每件都要做）

1. `cd frontend && npx tsc --noEmit -p tsconfig.json` → 0 错误（pre-existing 错误要单独说明）。
2. 逻辑测试：`npx vitest run <相关文件>`（DSH 沙箱常有 `spawn EPERM`，需本地跑）。
3. **浏览器实测**：页面截图 + 默认选中值 + 切换连接器后模型是否跟着默认模型。
4. 更新本文档的「状态」列 —— **迁移没登记 = 没做完**。

## 六、变更记录

- **2026-11-01**：新增 `pickDefaultConnector`（`is_default` 优先）。起因：角色详情「AI 补全」
  报 `All connection attempts failed` —— 列表第一个是没启动的本地反代
  `127.0.0.1:8317`，而用户标记的默认连接器「若海-qwen3.8-27b」排第二。
  已接入：`useLlmConnectors`、角色详情、图片生成「AI 优化」、`MultiPlatformGen`、
  小说世界、写作风格、书源。**用户截图确认**角色详情「图像供应商 / 模型」已合成一行渲染。

- **2026-10-31**：建文档并完成第一批收编。
  - `utils/modelSelection.ts` 成为唯一规则（兼容 `model` / `default_model`），视频页旧文件保留 re-export。
  - `ProviderModelSelect`：候选合并 + 默认模型优先 + `providerOptionLabel`；切换连接器时**即使解析为空也回调**，
    避免沿用上一个连接器的模型。
  - `useLlmConnectors` 改用统一规则。
  - 页面迁移：`character-detail`（立绘 + AI 补全）、图片生成「AI 优化」、`MultiPlatformGen`、
    `novel-world`、`WorldMapEditor`、`writing-styles`、`book-source`。
  - 未做：图片生成「高级设置」厂商 → 部署配置（语义不同，待设计）；`agent`/`story`/`canvas`（顺序已正确）。
  - 验证：`tsc --noEmit` 0 错误；浏览器实测 `multi-platform-gen`（LLM 模型已带默认值）、`video-gen`
    （模型显示 `agnes-video-2.5-flash`）；`character-detail` 与图片生成弹窗**画面未完成人工确认**
    （页面首编译慢 / 弹窗需先填提示词）。
