# 2026-08-29 接手总结（角色立绘多参考图 / 连接器热刷新）

## 项目目标

承接上一轮会话的收尾工作：角色立绘作为图片素材可被复用、通用生图后端支持多参考图、AI 连接器保存后立即生效。

## 环境状态（已启动）

- 后端 uvicorn：`127.0.0.1:8000`（`/docs` 200，`GET /api/v1/characters?skip=0&limit=1` 200）
- 前端 vite：`0.0.0.0:3000`（`vite.config.ts` 中 `server.port = 3000`，代理 `/api` → 8000）
- Alembic：`current = 028_add_character_relationship_world_time (head)`，与代码一致，无需补迁移
- 分支：`main`，领先 `github/main` 6 个提交

## 未提交改动（接手时的工作区脏改）

| 文件 | 内容 |
| --- | --- |
| `backend/app/api/v1/ai_connectors.py` | `reload_ai_service_after_connector_change` 由后台线程改为 `async` + `asyncio.to_thread`，写库后同步等注册表重建，消除"保存后立刻生图仍命中旧模型/旧 Key"的竞态 |
| `backend/app/services/ai/backends/image/generic.py` | multipart 请求支持 `image` 字段为列表（多参考图），并在 `request_content_type=multipart` 时把 `reference_images` 写入参考图字段 |
| `backend/app/api/v1/assets.py` | 资产列表 `type=image` 时一并返回 `CHARACTER` 节点（角色立绘主表示是图片，可被图转 3D 等选图入口使用） |
| `backend/app/api/v1/characters.py` | 关系接口补充 `CreativeProject` 导入（世界视角名称解析） |
| `backend/tests/test_character_management_redesign.py` | 关系响应断言补齐世界/时间维度字段（`world_usage_id`、`world_name`、`timeline_phase`、`chapter_number`、`related_character_name`） |
| `frontend/src/pages/character-detail/index.tsx` | 立绘尺寸改为动态选项；Prompt 工具区新增「生成主立绘」主按钮 |
| `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` | 3D 缩略图与上传入库描述修订 |
| `examples/ai-connectors/` | 新增 `chybenzun-gpt-image-2-edit.json` 供应商示例，README 同步登记 |

## 验证结果

- `pytest backend/tests/test_character_management_redesign.py backend/tests/test_character_provenance.py`：11 passed
- `GET /api/v1/characters/relationships/graph`：200
- `cd frontend && npm run build`：tsc + vite build 通过（仅有 chunk 体积告警）
- 迁移链 `023 → 028` 完整，数据库已在 head

## 接手复核发现的问题（本轮改动自带，尚未修）

1. **测试已挂（必改）**：`backend/tests/test_ai_image_async.py::test_generic_image_backend_sends_multipart_edit_request` 失败，`assert requests[0]["files"]["image"][0]` 抛 `TypeError: list indices must be integers`。原因：multipart 多图改动把 `files` 从 dict 改成了 list-of-tuples，测试断言未同步。全量跑该文件为 `1 failed, 20 passed`。
2. **资产列表分页回归**：`assets.py:514-522` 对多个 node_type 各取 `page/page_size` 并 `total += type_total`，`type=image` 现在命中 IMAGE + CHARACTER 两类 → 单页最多 2 倍数据、`total` 虚高、翻页会重复/漏项。且 `assets.py:540` 只对 `novel` 做了 type 兜底，`image` 没有，非图片主表示的 CHARACTER 节点会混入。
3. **静默退化风险**：`generic.py:224-225` 在 `multipart_payload is None` 时退回 `json=request_body`，而 `generic.py:888` 已把参考图字段写成数组（原来是单字符串）→ 命中该分支的供应商会收到数组，可能 400。另 `generic.py:887` 与 `889` 两个独立 `if` 同时命中时，数组字段会以 `str(list)` 形式进入表单 data（目前被 `ai_connector/service.py` 的归一化兜住，直接改库/旧 JSON 导入仍会中招）。
4. **连接器刷新（改动 3）判定安全**：4 处调用点均已 await，`AIService.initialize` 先在局部变量构建完再赋全局，无半初始化竞态。可选加固：给重建加 `asyncio.wait_for` 超时与 `asyncio.Lock`，避免慢 backend 拖慢写接口、并发保存重复全表重建。

## 用户报障诊断（2026-08-29）

### 问题 1：角色立绘生成不入任务中心/事件日志

根因：角色链路只写 `project_generation_logs`（角色详情页「生图日志」面板），从不写 `platform_event_logs`（任务中心三 Tab 与 `/api/v1/logs` 的数据源）。

- `characters.py:1555 / 1587 / 1700` 三处 `scene="character_portrait"` 全部走 `_write_project_generation_log`
- `characters.py` 没有 import `app.services.platform_log`（对比 `images.py:32` 有）
- 参照系：`images.py:728/804/827/862/885`、`videos.py:597/624/665`、`model3d_workspace.py:291/313/324/488`、`llm.py:28`、`creative_projects.py:127/169` 都写了 `platform_log.record_event`
- 缺口范围：不只是 `portrait/generate`，AI 补全（1420/1437/1462）和切片（1308/1330）同样缺失

注意 `logs.py:209-266` 的失败重发只识别 `scene` 为 `image` / `video` / `llm`，新增 scene 会命中 266 行「不支持的场景重发」。因此建议角色事件复用 `scene="image"` + `task_type="image_generation"`，在 message/request 里带 `character_id` 区分来源，这样任务中心可过滤且支持重发（重发只会重新出图，不回写角色）。

### 问题 2：角色立绘生图 400 image_url_fetch_failed

链路（`backend/app/services/ai/backends/image/generic.py`）：

1. 前端 `character-detail/index.tsx:827` 把 `[canonicalMainVisualUrl, ...referenceImages]` 作为 `reference_images` 提交；`canonicalMainVisualUrl` 取 `identity.visual_profile.identity_reference_url` 或 `character.portrait_url`（435-437 行），即数据库里存的 URL
2. `_prepare_params:656-660` 对 http(s) URL 直接透传，不下载也不校验可达性
3. `_render_request:887-888` 在 `request_content_type=multipart` 时把 `image` 写成**数组**
4. `_build_multipart_payload:811-812` 发现值是 http URL 直接 `return None`
5. `generic.py:224-225` 于是退化成 `json=request_body`，把数组原样发出 → 供应商收到 `"image": ["https://..."]`，期望字符串/文件 → 400

叠加的数据问题：本次报错的图 `https://image.zakowsl.cc.cd/files/00c161b5-....png` 本机 HEAD 请求返回 **404**，是死链。该域名在代码库中无引用，属于数据库里存的外链素材地址。所以即使修好数组问题，这张图也必然失败。另一张参考图走 `/api/...` 本地路径时在 `_url_to_base64:703-715` 下载超时，被 666 行 `warning` 静默吞掉，导致「生图成功但参考图悄悄丢失」。

修复方向分两层：

- 数据层：换掉角色身上的死链参考图，改用平台托管地址（`/api/v1/assets/...` 或 COS），不要把外部图床当持久存储
- 代码层：multipart 模式遇到 http(s) 参考图应先下载成 bytes 再作为文件字段上传，而不是退化成 JSON 数组；退化 JSON 时用 `reference_images[0]` 而非整个数组；参考图转换失败不要静默跳过，要进事件日志或显式报错

### 补充：数据库里实际生效的 edit 连接器配置（2026-08-29 复核）

库里有两个 gpt-image-2 图生图连接器，参考图形态完全不同：

| 连接器 | base_url / endpoint | 参考图形态 | 关键配置 |
| --- | --- | --- | --- |
| `aaccx-gpt-image-2-edit`（345e6a97） | `api.aaccx.pw/v1` `/images/edits` | **URL**（JSON） | `request_template` 写死 `"images":[{"image_url":"{{ reference_image_url }}"}]`，无 `request_content_type`，`support_multiple_reference_images=true` |
| `GPT Image-2 Edit（通用示例）`（2d859cb8，即本次报错的连接器） | `yyds.chybenzun.top/v1` `/images/edits` | **multipart 文件二进制** | `request_content_type=multipart`、`multipart_image_field=image`、`reference_image_field=image`、`support_multiple_reference_images=**false**`（与 `examples/ai-connectors/chybenzun-gpt-image-2-edit.json` 里的 `true` 不一致） |

注意代码不读 `support_multiple_reference_images`：`generic.py:887-888` 在 multipart 模式下无条件把 `image` 写成数组，与库里 `multi=false` 的语义冲突。

中转站文档 `https://yyds.chybenzun.top/custom/api_docs` 是 SPA（YM2API/new-api 面板），正文走自定义页面接口且需鉴权，尝试 `/api/doc`、`/api/custom_page/*`、`/api/page/*` 均 404，前端 bundle 内也无文档正文，未能取得原文。可用证据是供应商返回体：`{"code":"image_url_fetch_failed","param":"image"}` —— 说明它把 `image` 参数的值当图片地址去抓取。

## 本轮修复（2026-08-29）

### 修复 1：角色立绘生成入事件日志（问题 1）

`backend/app/api/v1/characters.py`：新增 `platform_log` import 与 `_portrait_event_payload` / `_portrait_retry_payload` 两个辅助函数；在 `portrait/generate` 的异常、供应商失败、成功三条路径各写一条 `record_event`。

- `scene` 复用 `image`、`task_type` 复用 `image_generation`：`logs.py:209-266` 的失败重发只识别 image/video/llm，新 scene 会命中「不支持的场景重发」
- message 带角色名；失败事件写 `retry_payload`（字段对齐 `ImageGenerationRequest`），可在事件日志详情里重发，重发只重新出图不回写角色

### 修复 2：multipart 参考图（问题 2）

`backend/app/services/ai/backends/image/generic.py`：

- `_build_multipart_payload` 支持 http(s) 与 `/api/...` 内部路径：先下载成字节，再按提交顺序重复提交 `image` 文件字段（网关不会替客户端抓取 URL）
- 新增 `_download_multipart_image`（30s 超时，失败返回 None）
- 全部参考图不可用时抛 `ValueError`，且构造过程移到重试循环之外，避免同一张坏图被重复下载三次；不再退化成网关不接受的 JSON `image` 数组
- `_render_request` 尊重 `support_multiple_reference_images`：不支持多图时只提交第一张
- 修正 `_decode_multipart_image` 解包顺序——httpx 的 files 元组是 `(文件名, 字节, MIME)`，之前把字节当成了文件名
- 影响面：库里只有 `2d859cb8` 一个连接器配了 `request_content_type=multipart`，其余供应商走 JSON 路径不受影响

测试：`backend/tests/test_ai_image_async.py` 新增 2 例（多图按序重复字段、参考图不可用时不发请求），修正 1 例断言；合计 `test_ai_image_async.py + test_platform_log_service.py + test_character_management_redesign.py` 33 passed。

## 第二轮修复：本机参考图直读 + 生图面板改造

新日志暴露了上一轮没堵住的洞：`转换参考图失败: 通过代理下载图片失败: timed out` → 参考图被静默丢弃 → 发出**没有参考图**的图生图请求 → 网关 `400 images[].image_url is required`。

### 根因

岳瑶的 `identity_reference_url` 与 `reference_image_urls[0]` 都是平台内部地址 `/api/v1/assets/download?path=F:\...\20260828_233828_...png`（1.7MB，本机文件）。`_url_to_base64` 对 `/api/...` 走 HTTP 回环下载（`BASE_URL` 默认 `http://localhost:8000`），后端繁忙或 localhost 解析到 IPv6 时 30 秒超时，异常在 666 行被 `warning` 吞掉，参考图整批消失。

### 后端：本机文件直接读取

- 新增 `backend/app/services/asset_file_resolver.py`（服务层）：`resolve_asset_file_from_url()` 把 `/api/v1/assets/download?path=...`、`/api/v1/assets/file?path=...` 还原成本机路径，复用与 `assets.py::_asset_file_allowed_roots` 一致的允许根目录与临时目录白名单做越界校验，越界/不存在返回 None。文件本就在本机，不再绕一圈 HTTP。
- `generic.py::_url_to_base64` 的 `/api/` 分支与 `_download_multipart_image` 都先尝试本机直读，失败才回退网络下载；回退默认地址改为 `http://127.0.0.1:8000`，避免 localhost 解析到 IPv6。
- `_build_multipart_payload` 新增 `require_image` 参数：图生图（请求带 `source_image` 或 `reference_images`）却没有一张可用参考图时直接报「图生图请求没有可用参考图」，不再发出网关必然拒绝的空请求；纯文生图保持原来的「无参考图则退化 JSON」行为。
- 测试：`test_ai_image_async.py` 新增本机直读用例（patch `httpx.Client` 断言不发起 HTTP），共 24 passed。
- 实测：岳瑶的主视图与参考图均可解析为本机文件（1,725,689 bytes）。

### 前端：生图面板（`frontend/src/pages/character-detail/index.tsx`）

- 新增「生成模式」Segmented：图生图（携带参考图）/ 文生图（不携带参考图）。文生图不传 `reference_images`，由后端按能力走 `/images/generations`。
- 供应商与模型下拉按模式过滤：`/api/v1/images/backends` 返回的 `capabilities` 含 `text_to_image` / `image_to_image`，切换模式后若当前供应商不支持新模式，自动落到第一个可用供应商。
- 新增参考图选择器：主视图 + 参考图集合以缩略图网格展示，逐张勾选，未选中的置灰，主视图带标签；勾选顺序即提交顺序（对应网关的图 1、图 2……）。默认全选，用户取消过的不会因列表刷新被重新选中（用 `seenReferenceUrls` ref 记录已见过的 URL），新加入的图自动补为选中。
- 「Prompt 预览」弹窗新增参考图区块，按图 1、图 2…… 展示本次会提交的图及数量；文生图模式提示不携带参考图。
- `npm run build`（含 `tsc --noEmit`）通过。

## 第三轮：收口与本轮闭环验证

### 素材库跨类型分页回归（上一轮改动引入）

`assets.py::_list_asset_hub_cards` 在 `type=image` 同时命中 IMAGE 与 CHARACTER 时，原来「每类各取一页」导致单页最多返回 `2 × page_size` 条、翻页重复或漏项，且只有 novel 有类型兜底。改为：多类型时按「当前页累计条数」取候选（`page * page_size`），合并、按 `_sort_created_at` 倒序后统一切片；并给 image 补上类型兜底，非图片主表示的 CHARACTER 节点不再混入。

### 角色 AI 补全事件日志

`characters.py` 的 AI 补全三条路径（供应商失败 / 返回解析失败 / 成功）补 `scene=llm` + `task_type=llm_chat` 平台事件。立绘切片是本地图像处理、不调用外部供应商，按「平台事件记录供应商调用」的定位保持只写 `ProjectGenerationLog`。

### 归一化规则修正：multipart 不再强制关闭多图

`ai_connector/service.py::normalize_reference_image_config_values` 在 multipart 分支写死 `support_multiple_reference_images = False`，导致通过 API 打开开关后又被强制回写（PUT 返回 200 但读回来仍是 False）。该假设与网关规范 §5.2（重复 image 字段支持最多 15 张）冲突，改为保留连接器声明值；同步更新 `test_ai_image_async.py` 中被这条旧假设锁住的断言，并补一例「声明单图时不擅自开启多图」。随后把 `2d859cb8` 的 `support_multiple_reference_images` 打开，读回为 True。

### 端到端验证

岳瑶角色以本机立绘为参考图做图生图（1024x1024，1K 档）：

- 生成成功，返回 `version_number=3`，新文件 `20260829_033645_输出主立绘..._0.png`，已入资产中枢（node_id / version_id / representation_id）
- 事件日志写入 `image_generation | 角色立绘生成成功：岳瑶 | 30039 ms`
- 整条链路：本机参考图直读 → multipart 重复 image 字段上传 → 网关返回 → 入资产中枢 → 事件落账

测试：43 passed（生图后端、角色管理、角色溯源、平台事件日志）。
文档：`docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` 补充跨类型分页语义与角色生图参考图/落账链路；`openspec/changes/platform-event-logging/tasks.md` 16A.2 勾选。

## 待办任务

- `character-management-redesign` 未勾选项：2.1（角色列表卡片升级为"角色册"视图）、2.3（Bible 分区组件重构为紧凑网格）、5.2（前端浏览器验收：角色册列表、独立角色页、关系图谱、Prompt 面板）
- 本轮改动尚未做浏览器端人工验收：多参考图生图、角色立绘在图转 3D 选图中的表现、连接器保存后立即生图

## 关键决策

- 连接器刷新改为同步等待，牺牲一点接口响应时间换取"保存即生效"的一致性
- 角色立绘继续存在 `CHARACTER` 节点上（保留版本与身份元数据），仅在列表查询层按图片类型一并放出，不改存储结构

## 下一步建议

1. 浏览器验收本轮三项改动（多参考图 / 立绘选图 / 连接器热刷新）
2. 或继续 `character-management-redesign` 的 2.1、2.3 前端任务
