# 设计

## 1. 分层模型

```text
独立能力层
  文本 / 图片 / 视频 / 3D / 配音 / 图片编辑 / 下载 / 采集
        ↓
素材中枢与血缘
        ↓
编排层
  创作项目 / 生产方案 / 创作画布 / 3D 预演 / 导演 Agent
        ↓
输出适配层
  小红书 / 抖音 / 微信 / B站 / 绘本 / 视频 / 发布草稿
```

生产方案只描述推荐步骤、输入输出、可跳过节点和检查规则，不拥有独立的生成实现。

## 2. ContentProductionProfile

建议先存放在项目 `settings`，成熟后再独立建表：

```json
{
  "id": "storybook",
  "label": "故事绘本/漫画",
  "goal": "page_illustrated_story",
  "recommended_stages": ["story_seed", "page_plan", "character_pack", "storyboard", "image", "layout"],
  "optional_stages": ["prose", "voiceover", "video"],
  "default_outputs": ["comic_pages", "image_set"],
  "constraints": {"page_count": 12, "aspect_ratio": "4:3"}
}
```

首批方案：

- `vertical_drama`：竖屏短剧
- `storybook`：恐怖漫画、童话绘本、故事绘本
- `knowledge_content`：科普图文/视频
- `platform_note`：平台图文内容
- `novel_serial`：小说连载
- `single_shot`：单镜头或单页实验

小红书、抖音、微信等不作为 profile，而作为 `output_adapter`，调用现有多平台生图、图片编辑、视频剪辑和发布能力。

## 3. 导演 Agent 与 Skill Team

导演 Agent 负责目标澄清、生产方案选择、阶段计划、上下文装配、依赖检查、结果汇总和用户确认；专业 Skill 负责单一职责：

- `story-designer`：故事种子、冲突、节拍、反转
- `script-writer`：脚本、对白、旁白、平台文案
- `visual-director`：视觉风格、镜头语言、构图、光线
- `character-director`：角色设定、参考包、一致性约束
- `storyboard-director`：页纲、镜头表、分镜和画面提示词
- `image-producer`：选择连接器、生成图片、保存 Asset Hub 血缘
- `video-producer`：首帧、动作提示、视频任务和回流
- `platform-adapter`：平台比例、页结构、标题、标签和导出
- `editorial-reviewer`：连续性、事实、节奏和发布前检查

运行时使用已有 `TeamComposer` / `SubagentOrchestrator`，每个角色独立 Run，结果以结构化 observation 汇合。导演不直接吞并所有 Skill 的职责。

## 4. 对话式生成

推荐交互：

```text
用户目标
  → 导演识别内容方案与缺口
  → 输出可编辑生产计划
  → 用户确认或修改
  → 分阶段执行并进入任务中心
  → 每阶段产物可预览、重生成、替换、入素材库
```

图片生成前展示的是“规划摘要”而不是隐藏思维链：

```json
{
  "intent": "建立主角第一次看见古堡的恐怖感",
  "reference_assets": ["character:...", "location:..."],
  "prompt": "...",
  "negative_prompt": "...",
  "provider": "...",
  "model": "...",
  "expected_output": "storyboard_frame"
}
```

用户可以在对话中说“换成童话风”“只改第三格”“保留角色脸型”“换成小红书封面比例”，导演只重跑受影响的节点。

## 5. 去标记/元数据清理

外部 `watermarks-remover` 计划接入为可选本地服务或 Agent Skill：

- 文本：不可见 Unicode、双向控制符、标签字符和可检测的统计标记清理/检查。
- 文件：PNG/JPEG/WebP/AVIF/HEIC/BMP/GIF/TIFF、SVG、PDF、Office、EPUB、HTML、Markdown、MP4/MOV/M4A/M4V、WAV/MP3/FLAC 等文件的 C2PA/EXIF/XMP/文档属性审计与清理。
- 结果必须保留原文件、清理后版本、操作 provenance、授权/来源标记和处理日志。
- UI 文案使用“AI 来源标记与文件元数据清理”，不要宣称能移除所有视觉水印。

它和现有能力的边界：

- `crawler/fetch-no-watermark`：从支持的平台获取授权可用的无水印远程媒体。
- `image-editor`：用户主动编辑图片、裁切、缩放、加水印和格式转换。
- 新 Skill：对用户已有文件做来源标记/元数据审计和清理。

## 6. 审计与安全边界

- 所有导演计划、Skill 路由、输入资产、提示词、模型、输出资产和失败原因写入任务/事件日志。
- 生成、下载、清理和发布等消耗型或外部写入动作继续走确认机制。
- 清理操作默认生成副本，不覆盖原文件。
- 失败可从事件日志查看 provider、model、请求摘要、诊断和重试参数。
