# 不明中转站生图调用说明（文生图 / 图生图）

面向外部智能体（WorkBuddy 等）的调用契约。**推荐通过 YLCraft 平台 API 调用**——密钥由平台保管，外部 Agent 不读取、不传递供应商凭证（见 `external-agent-api.md`）。直连参数附在文末，仅供排查。

本文件里的每条结论都是**实测**得出的，已标注验证时间与实测数据。

## 一、两个连接器，分工明确

平台里"不明中转站"是**两个**连接器，一个管文生图、一个管图生图：

| | 文生图 | 图生图 |
| --- | --- | --- |
| 连接器名（`provider`） | `不明中转站-gpt-image-2` | `不明中转站- Image-2 Edit` |
| 模型（`model`） | `gpt-image-2` | `gpt-image-2` |
| 上游端点 | `POST /v1/images/generations` | `POST /v1/images/edits` |
| 请求体 | JSON | **multipart/form-data** |
| 参考图 | **不支持** | 支持，字段名 `image`（**单张**） |
| 可用尺寸 | `2048x2048`、`1152x2048`、`2048x1152` | `1024x1024`、`1536x1024`、`1024x1536`、`2048x2048`、`2048x1152`、`1152x2048`、`3840x2160`、`2160x3840` |

> **注意尺寸不通用**：文生图那三个尺寸用不了在 `3840x2160` 上，反之亦然。传错尺寸不一定报错，可能被上游静默改成别的尺寸。

## 二、通过 YLCraft 平台调用（推荐）

### 1. 先查能力（确认可用与尺寸）

```bash
curl "http://127.0.0.1:8000/api/v1/ai/capabilities?available_only=true"
```

返回 `{"success": true, "type": ..., "capabilities": [...]}`，`capabilities` 是**扁平列表**（不按类型分组），按 `type` 字段区分 `llm` / `image` / `video` / `3d` / `embedding`。**不返回密钥**（只有 `has_api_key: true/false`）。

单个条目实测形状（`不明中转站- Image-2 Edit`）：

```json
{
  "id": "2d859cb8-…",
  "name": "不明中转站- Image-2 Edit",
  "provider": "chybenzun-image",
  "type": "image",
  "model": "gpt-image-2",
  "available_models": ["gpt-image-2"],
  "base_url": "https://yyds.chybenzun.top/v1",
  "api_endpoint": "/images/edits",
  "api_format": "custom",
  "has_api_key": true,
  "is_default": false,
  "status": "available",
  "capabilities": ["image_to_image"],
  "supported_sizes": ["1024x1024", "1536x1024", "…"],
  "support_reference_image": true,
  "support_multiple_reference_images": false
}
```

挑连接器时看这四个字段：

- **`name`** —— 传给 `/images/generate` 的 `provider` 用的就是它（**不是** `provider` 字段，那个是供应商标识 `chybenzun-image`）
- **`type: "image"`** —— 只要生图连接器
- **`capabilities`** —— `["text_to_image"]` 只能文生图；含 `image_to_image` 才能收参考图
- **`supported_sizes`** —— 尺寸必须从里面选

> **`is_default` 全库都是 `false`**：没有任何连接器被标为默认。所以**必须显式传 `provider` + `model`**——不传时后端会回落到"第一个可用的"，落到谁是不确定的。

### 2. 文生图

```bash
curl -X POST http://127.0.0.1:8000/api/v1/images/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A quiet empty classroom in late afternoon light, wooden desks in rows",
    "provider": "不明中转站-gpt-image-2",
    "model": "gpt-image-2",
    "size": "2048x2048",
    "n": 1,
    "project_id": "<可选，用于把产物归到项目>"
  }'
```

### 3. 图生图（参考图）

两种传参考图的方式，任选：

**方式 A：传素材库资产 ID（推荐，稳定引用）**

```bash
# 先上传：POST /api/v1/assets/upload  (multipart: file=@a.png)
curl -X POST http://127.0.0.1:8000/api/v1/images/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "same scene, change the time of day to night",
    "provider": "不明中转站- Image-2 Edit",
    "model": "gpt-image-2",
    "size": "1024x1024",
    "n": 1,
    "reference_asset_ids": ["<上传后得到的 asset_id>"]
  }'
```

**方式 B：传项目视觉基准（一项目一张，自动注入）**

若项目已设视觉基准（见 `external-agent-api.md` 的项目端点；UI 入口在「小说世界」页），则**只要带 `project_id` 就会自动作为参考图注入**，无需显式传参考图：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/images/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "same scene, change the time of day to night",
    "provider": "不明中转站- Image-2 Edit",
    "model": "gpt-image-2",
    "size": "1024x1024",
    "project_id": "<已设视觉基准的项目>"
  }'
```

> 基准**只在目标连接器支持图生图时才注入**。用文生图连接器带 `project_id` 是安全的：不会因项目设过基准就把请求变成图生图而失败。

### 4. 响应与后续

**响应是平铺的，没有 `data` 包一层**（端点上直接返回 `ImageResponse`）：

```json
{
  "success": true,
  "url": "https://yyds.chybenzun.top/upscale1/files/….png",
  "urls": ["…"],
  "asset_id": "5054d860-…",
  "all_asset_ids": ["…"],
  "asset_hub_node_id": "…",
  "local_path": "…",
  "provider": "不明中转站-gpt-image-2",
  "model": "gpt-image-2",
  "status": "succeeded",
  "planning_summary": { "reference_assets": ["…"], "…": "…" }
}
```

判定成败看**顶层 `success`**；失败时看 `error`。注意：

- **图生图的产物 URL 常是平台内地址**（`/api/v1/assets/download?path=…`），文生图那次拿到的是上游直链——两种都要能处理。
- `planning_summary.reference_assets` 记录的是**请求里显式传的**参考资产，不含自动注入的项目视觉基准（基准走的是内部合并，不进这个字段）。想确认基准有没有生效，别只看这里。

后续：

- 产物已落素材库，用 `GET /api/v1/assets/{asset_id}` 取元数据
- 失败排查用 `GET /api/v1/logs`（含 provider、model、错误诊断、重试链）
- 异步任务用 `GET /api/v1/tasks/{task_id}`

### 5. 鉴权

本机部署默认**不要求** Key。若设置了 `YLCRAFT_EXTERNAL_API_REQUIRE_KEY=1` 则必须带：

```bash
-H "Authorization: Bearer ylk_xxxxxxxx"
```

Key 管理见 `external-agent-api.md`（`ylk_` 明文只在创建时返回一次）。

## 三、实测结果（2026-09-15）

| 场景 | provider | 结果 | 用时 |
| --- | --- | --- | --- |
| 文生图 | `不明中转站-gpt-image-2` | ✅ 成功 | 43.4s |
| 图生图（中性 prompt + 参考图） | `不明中转站- Image-2 Edit` | ✅ 成功 | 38.6s |
| 图生图（含"小男孩"的 prompt + 男孩参考图） | `不明中转站- Image-2 Edit` | ❌ 400 | 141.9s |

### 必须知道的一条约束：内容审核

失败那次的响应体是：

```json
{"error": {"code": "content_policy_violation",
           "message": "Upstream request failed. Please retry later.",
           "type": "upstream_error"}}
```

**注意 `message` 是误导性的**（"请稍后重试"），真实原因是 `code: content_policy_violation`。判别测试把范围缩小到了**组合**：

| 变量 | prompt | 参考图 | 结果 |
| --- | --- | --- | --- |
| A | 含"小男孩" | 无 | ✅ 通过 |
| B | 中性（空教室，无人物） | 男孩图 | ✅ 通过 |
| C | 含"小男孩" | 男孩图 | ❌ 被拒 |

**单独都能过，组合起来被拦。** 上游（gpt-image 系）对涉未成年人的**图像编辑**审核明显比纯文本生图严。

实际影响：画儿童题材漫画时，凡"以儿童图为参考 + prompt 里点名儿童"的图生图请求都可能被拒。可行的绕法（未逐一实测）：

- 参考图不含人物（用场景/背景/画风图当基准），人物交给 prompt 描述；
- 或该页改用文生图 + 详细人物描述；
- 或换用支持参考图、且审核策略不同的连接器（如 `Agnes Image 2.1 Flash`）。

## 四、直连参数（仅供排查，不含密钥）

密钥在平台连接器里保管，外部 Agent **不应**读取或传递。若确需直连排查，从平台「AI 连接器」页取 Key，不要写进代码或文档。

```bash
# 文生图
curl -X POST https://yyds.chybenzun.top/v1/images/generations \
  -H "Authorization: Bearer <key>" -H "Content-Type: application/json" \
  -d '{"model":"gpt-image-2","prompt":"…","size":"2048x2048","n":1}'

# 图生图（multipart）
curl -X POST https://yyds.chybenzun.top/v1/images/edits \
  -H "Authorization: Bearer <key>" \
  -F "model=gpt-image-2" \
  -F "prompt=…" \
  -F "size=1024x1024" \
  -F "n=1" \
  -F "quality=auto" \
  -F "response_format=b64_json" \
  -F "image=@reference.png"
```

响应字段：`data[*].url` 或 `data[*].b64_json`（本连接器配的是 `response_format=b64_json`）。

## 五、给外部 Agent 的三条硬要求

1. **必须显式传 `provider` 和 `model`**。不传时后端按「指定名 → 指定模型 → 系统默认 → 第一个可用的」回落，而当前库里**没有任何连接器被标为默认**，等于落到谁是不确定的——会出现"以为在用 A、实际跑了 B"。
2. **参考图与连接器能力要匹配**。把参考图发给纯文生图连接器会被 **400** 拒绝（错误文案是「指定的 Provider 'X' 不支持图生图功能」）。
3. **别把 `content_policy_violation` 当网络问题重试**。它是内容审核，重试无用；按上面第三节的绕法调整 prompt 或参考图。
