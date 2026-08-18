# Tasks

调研已完成，代码尚未进入实现阶段。以下为后续落地任务清单（按推荐路线 A 优先）。

- [ ] 1. 调研腾讯云「查询绑骨蒙皮任务」接口（`DescribeAutoRiggingJob` 或等价轮询接口）的请求/响应契约，确认与 `SubmitAutoRiggingJob` 的配对方式。
- [ ] 2. 在 `Model3DConnectorBackend` 或其扩展中，新增绑骨蒙皮的 submit/poll/download 能力（复用 TC3 签名与 `response_config` JSONPath 契约）。
- [ ] 3. 设计绑骨蒙皮的数据模型与任务账本：复用 `Model3DGenerationTask` 或新增独立账本，记录 `source_asset_id`（原始 GLB）、`motion_type`、`provider_task_id`。
- [ ] 4. 新增 API：提交绑骨任务、轮询状态、历史记录，并复用 Asset Hub 回流（rigged GLB 作为 `3d_model` 资产，`derived_from` 指向原始静态模型）。
- [ ] 5. 前端将「骨骼绑定方案」占位开关接入真实提交：勾选「接 API」后，在图生 3D 完成后（或对已有资产）发起绑骨，展示预设动作选择与结果预览（`Model3DViewer` 渲染骨骼动画）。
- [ ] 6. 接入「文生动作」「3D 人物生成」等其余混元下游能力（可选，按产品优先级）。
- [ ] 7. 评估路线 B（本地 UniRig）与路线 C（Studio 手动）是否需要长期保留为入口，或仅作为文档链接保留。
- [ ] 8. 真实供应商验收：用已开通的腾讯云账号跑通「图生 3D → 绑骨蒙皮 → 带骨骼模型入库 → 查看器渲染」全链路，记录诊断与费用。
- [ ] 9. 同步更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` 与 `docs/architecture/API_SURFACE.md`（若新增接口）。
