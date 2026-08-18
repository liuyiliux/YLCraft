# Design

- 绑骨蒙皮是「图生 3D」的下游能力，不是独立的第二个 3D 生成工作台；输入是已入库的 `3d_model` 资产（GLB/FBX），输出是带骨骼的 `3d_model` 资产，`derived_from` 指向原始静态模型。
- 接口复用腾讯混元 `ai3d.tencentcloudapi.com` 域名、Version `2025-05-13` 与 TC3-HMAC-SHA256 签名，与现有图生 3D 的 `Model3DConnectorBackend` 保持一致；能力由 `response_config` 的 JSONPath / Action 名显式声明，不把 endpoint 名当能力。
- `SubmitAutoRiggingJob` 输入 `File3D.Url`（FBX/GLB，≤60MB）+ 可选 `MotionType`（48 种预设动作），输出 `JobId`（有效期 24h）；需配合「查询绑骨蒙皮任务」轮询接口获取最终模型 URL。
- 复用现有任务账本与 Asset Hub 回流约定：本地短 id 做主键，opaque `provider_task_id` 存 `result_json`；完成时下载模型并建 `AssetNode(3d_model) -> AssetVersion -> AssetRepresentation`，若源是资产则建 `derived_from`。
- 三种候选路线在 UI 上以「开关 + 跳转链接」呈现：接 API（真实调用，路线 A）、本地 UniRig（占位，需 GPU 基础设施）、混元 Studio 手动 rig（外部人工流程）。当前阶段三者均为占位，不触发真实调用。
- 2D 口型驱动数字人（SadTalker/MuseTalk/EchoMimic/LiveTalking）属「本地 GPU 重推理」，与当前轻后端架构冲突，单独立项并确认硬件后再评估，不并入本 change。
