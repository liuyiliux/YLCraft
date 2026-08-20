# 3D 导演预演台

## 背景

YLCraft 已有项目分镜、Asset Hub、3D 模型生成/绑骨和独立创作画布，但创作者仍需要在自然语言 Prompt 中猜测角色站位、物品比例和机位关系。外部参考项目 `storyai-3d-director-desk` 证明，轻量 3D 构图预演可以在 AI 生图/生视频之前提供更稳定的空间参考；`kunpeng-director` 进一步证明，稳定对象 ID、人工锁定和可验证操作是后续 Agent 控制预演的基础。

## 目标

建立一个与项目分镜面板关联的 3D 预演场景，让用户能够：

1. 从 `/story` 的分镜面板打开或创建对应预演场景。
2. 使用 Asset Hub 模型、轻量人物占位、基础几何体、全景背景和机位完成静态构图。
3. 在导演视角与机位视角之间切换，使用安全框和九宫格检查构图。
4. 截取当前机位画面，保存为 Asset Hub 图片并回流到当前分镜面板，作为既有生图/视频链路的参考图。
5. 为后续 24fps 关键帧、Agent 受控操作和镜头预演保留稳定的数据契约。

## 非目标

- 不替代 Blender、Unreal、Maya 等专业 DCC 工具。
- 本变更不实现复杂 IK、物理、地形雕刻、网格编辑或专业渲染。
- 本变更不实现关键帧时间轴、MP4 导出或 Agent 写操作；这些属于后续阶段。
- 不复制 `/story`、Asset Hub 或 `/canvas` 的事实，不创建第二份项目分镜或素材库。

## 设计原则

- 预演场景是独立持久化文档，通过 `project_id`、`storyboard_content_id`、`panel_number` 与既有分镜关联。
- 场景节点只引用 `asset_id`，不复制二进制资产。
- 节点、相机和未来关键帧使用稳定 ID；锁定状态属于业务数据。
- 截图必须通过 Asset Hub 和 `ProjectAssetLink` 回流，保留 `previs_scene_id`、`camera_id`、场景 revision 等 provenance。
- 当前阶段优先验证“静态构图截图能稳定进入分镜生成链路”，不让视频导出阻塞核心价值。

## 参考与许可

参考项目清单和许可证注意事项见 `docs/architecture/3D_DIRECTOR_PREVIS_DESIGN.md` 与 `F:\PycharmProjects\YLCraft-refs\README.md`。本变更只采用交互和数据建模思想，不复制外部源码。特别是 `awplanet` 的 PolyForm Noncommercial License 不允许未经授权的商业代码搬运。
