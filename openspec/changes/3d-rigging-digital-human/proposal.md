# 3D 骨骼绑定与数字人

## 背景

现有 `/model-3d` 图生 3D 工作台（`provider_type: "3d"`，配置驱动连接器，走腾讯混元 TC3 签名）产出的是**静态网格**（GLB/OBJ/FBX），无骨骼、无蒙皮、无动画。产品希望在「图生 3D」之后继续延伸「骨骼绑定 → 数字人」能力，让生成的角色能「动起来」。

本文记录截至 2026-08-18 的调研结论与三条候选路线，供后续 AI 接手时避免重复调研。

## 关键事实（已确认）

1. **腾讯混元生 3D 已原生提供「绑骨蒙皮」接口**：`SubmitAutoRiggingJob`（域名 `ai3d.tencentcloudapi.com`，Version `2025-05-13`，与现有 `SubmitHunyuanTo3DProJob` 完全同域名同版本同 TC3 签名）。
   - 输入 `File3D`（FBX/GLB，≤60MB），可选 `MotionType`（48 种预设动作：待机/走路/奔跑/街舞/回旋踢等）。
   - 输出 `JobId`（有效期 24h），经「查询绑骨蒙皮任务」接口轮询得到带骨骼模型。
   - 约束：人形需 A-Pose/T-Pose，不带武器/坐骑/翅膀等外部组件。
   - 参考文档：https://cloud.tencent.com/document/product/1804/131618
2. 混元生 3D 还提供「文生动作」「3D 人物生成」「智能拓扑」「纹理生成」「UV 展开」「组件生成」「格式转换」等下游能力（产品概述：https://cloud.tencent.com/document/product/1804/120696）。
3. 项目当前**无本地重模型推理基础设施**：`backend/requirements.txt` 无 `torch`，无 GPU 假设；后端是「轻后端 + 配置驱动调外部 API」模式。
4. 现有 Live2D 的「绑骨（`rigging.py`）/口型（`lip_sync.py`）」是**纯代码占位**（固定比例估算、RMS 近似），`mesh`/`physics` 接口返回 501，不是可依赖的真实能力。

## 三条候选路线

| 路线 | 做法 | 与现有架构贴合度 | 成本/风险 |
| --- | --- | --- | --- |
| A. 接 API | 复用现有 `Model3DConnectorBackend` 配置驱动模式，新增绑骨蒙皮/文生动作能力 | 最高，架构零改动、纯加配置 | 低（需腾讯云开通对应接口） |
| B. 本地跑 UniRig | 开源 MIT（清华+Tripo），本地部署 `torch + CUDA GPU ≥ 8GB` | 低，需引入全新本地推理基础设施 | 高（需 GPU 服务器） |
| C. 混元云端 Studio 手动 rig | 用户在混元 3D Studio 手动绑骨再导出 | 低，人工离线流程，无法程序化 | 无自动能力 |

- 开源参考：UniRig（https://github.com/VAST-AI-Research/UniRig ，MIT，输入 GLB/OBJ/FBX/VRM → 输出骨架+蒙皮 rigged 模型）。
- 2D 数字人口型驱动（独立方向，非本 change 主目标）：SadTalker / MuseTalk / EchoMimic / LiveTalking 等，均属「本地 GPU 重推理」，若要落地需单独立项并确认硬件。

## 推荐

优先落地**路线 A（接混元绑骨蒙皮 API）**：与现有图生 3D 实现模式完全同构，可复用连接器/TC3 签名/任务账本/Asset Hub 回流的既有代码，产出 rigged GLB 可直接被现有 `Model3DViewer` 渲染。

## 当前状态

- 已在 `frontend/src/pages/model-3d/index.tsx` 增加「骨骼绑定方案」**占位区块**：三条路线各带 Switch + 跳转链接，暂不接真实调用。
- 后端未改动。
