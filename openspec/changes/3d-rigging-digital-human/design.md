# Design

## 能力定位

- 绑骨蒙皮是「图生 3D」的下游能力，输入是已入库的 `3d_model` 资产（GLB/FBX）或公开模型 URL，输出是带骨骼的 `3d_model` 资产，`derived_from` 指向原始静态模型。
- 绑骨蒙皮拆成两种独立调用（同一入口选择器切换）：
  - **纯绑骨蒙皮**：只传 `File3D`，不传 `MotionType` → 输出仅带骨骼、无动作的 rigged 模型。
  - **绑骨蒙皮 + 预设动作**：额外传 `MotionType`（1-48）→ 输出带骨骼 + 套好预设动作的模型。

## 连接器契约（配置驱动）

- 复用腾讯混元 `ai3d.tencentcloudapi.com` 域名、Version `2025-05-13` 与 TC3-HMAC-SHA256 签名，与现有图生 3D 的 `Model3DConnectorBackend` 保持一致。
- **能力由 `response_config.capability` 显式声明**，不把 endpoint 名当能力：
  - `generation`（默认）→ 图生/文生 3D，action 为 `SubmitHunyuanTo3DProJob` / `QueryHunyuanTo3DProJob`。
  - `rigging` → 绑骨蒙皮，action 为 `SubmitAutoRiggingJob` / `DescribeAutoRiggingJob`（**注意是 `Describe` 前缀**）。
- 绑骨 `request_template` 用 Jinja 条件渲染实现 `MotionType` 可选：
  ```
  {"File3D":{"Url":"{{ image_url }}","Type":"{{ FileType | default('GLB') }}"}{% if MotionType %},"MotionType":{{ MotionType }}{% endif %}}
  ```
- `SubmitAutoRiggingJob` 输入 `File3D.Url`（FBX/GLB，≤60MB）+ `File3D.Type` + 可选 `MotionType`，输出 `JobId`（有效期 24h）；`DescribeAutoRiggingJob` 轮询，`Status` 取 `WAIT/RUN/FAIL/DONE`，结果在 `ResultFile3Ds`（含 `PreviewImageUrl`），Url 有效期 1 天。

## 任务账本与谱系

- 复用 `Model3DGenerationTask`，新增 `kind` 字段（`generation` / `rigging`）区分能力；本地短 id 做主键，opaque `provider_task_id` 存 `result_json`。
- 完成时下载模型并建 `AssetNode(3d_model) -> AssetVersion -> AssetRepresentation`，若源是资产则建 `derived_from`。
- 绑骨任务的 `request_json` 记录 `source_asset_id`、`source_url`、`motion_type`、`file_type`；`lineage.source` 用 `rigging`（生成任务用 `image_to_3d`）。

## 源模型公开 URL（绑骨专用）

- 腾讯绑骨接口仅接受**公开可访问**的模型 URL，本地资产文件需复制到 `storage/model3d/public/` 并经 `/model3d-files` 静态挂载暴露。
- `_resolve_rig_source` 负责：`source_url` 直接透传；`source_asset_id` 则查最新 `AssetRepresentation.file_path`，校验扩展名（仅 GLB/FBX），复制到 public 目录后拼装公开 URL。

## 素材库骨骼识别

- 上传（`assets.py`）与生成/绑骨回流（`model3d_workspace.py`）统一调用 `Model3DService.extract_metadata` 提取 `bones`/`animations`。
- 结果写入 `metadata_json`：`has_bones`/`has_animations`（`_rigging_flags`），并打标签 `rigged`/`animated`，供素材库徽标与筛选（覆盖「混元 Studio 手动绑骨后上传」的路线 C 场景）。

## UI 设计（阶段 2，待实现）

- `/model-3d` 重构为「3D 创作工作台」：两步走（创建模型 → 让模型动起来）+ 素材库网格。
- 绑骨入口用 Segmented 选择器切换「仅绑骨 / 预设动作」，预设动作从 48 种中下拉选择；服务商选择器从 `/backends?capability=rigging` 读取。
- `Model3DViewer` 增强 `useAnimations` 实际播放骨骼动画。
- 素材库卡片展示「静态 / 已绑骨 / 带动画」徽标并支持筛选。
