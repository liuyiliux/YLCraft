# 对话式生成能力盘点：我们支持 / 不支持什么（2026-10-15）

> 起因：所有者指出 ——
> 「我们现在主要是**智能体那的样式臃肿**；别的（平台）是**在对话框里可以加图片**
> （可能是素材库-资产对应的渲染），然后**告诉 AI 第几秒第几秒生成什么**；
> **我们应该是不支持的**。」
>
> 本文件是**代码级核对结果**。结论比"不支持"更细致：
> **数据模型大半已经有了，缺的是对话入口。**

---

## 结论速览

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 对话里**贴图/传附件** | ❌ **完全没有** | 前后端均无附件字段 |
| 对话里**引用素材库资产** | ❌ 不能直接指定，只能靠文字让 Agent 搜 | 有 `search_assets`，但无"这张图"入口 |
| 生成工具**接受参考资产** | ✅ **支持** | `generate_image_asset(reference_asset_ids=…, character_ids=…)` |
| 分镜**每格有秒数** | ✅ **支持** | panel 有 `duration_seconds`（3-6 秒） |
| 分镜**每格有运镜** | ✅ **支持** | `camera_motion`（推近/拉远/摇镜/平移/跟拍/环绕/静止） |
| 分镜格**显示已生成视频 + 时长** | ✅ **支持** | `storyboard-parts.tsx` L329-367 |
| 分镜格**跳转视频生成** | ✅ **支持** | 带 `source_type=storyboard_panel&source_index=…` |
| **对话里按"第几秒"下指令** | ❌ **没有** | 对话与时间轴无关联 |
| **对话里操作某一格/某一段** | ❌ **没有** | 无"选中某格"的对话上下文 |

---

## 一、对话加图片：确实完全不支持（前后端双证）

### 前端

`frontend/src/pages/agent/index.tsx` 全文件搜
`Upload | upload | attach | paste | drag | 图片 | 文件` ——
**只命中图标名（`PictureOutlined`）、分类标签（`image: 'AI 生图'`）和 `Empty` 组件**，
**没有任何上传/粘贴/拖拽入口**。

### 后端

`backend/app/api/v1/agent.py` L40-47：

```python
class ChatRequest(BaseModel):
    message: str                       # ← 只有一个字符串
    thread_id: Optional[str] = None
    session_id: Optional[str] = None
    context: dict = Field(default_factory=dict)
    stream: bool = True
    profile_id: Optional[str] = None
    force_new_thread: bool = False
```

**没有 `attachments` / `images` / `asset_ids` 字段。** 前端就算做出来也无处可传。

### 但生成工具本身是支持的

`backend/app/services/agent/tools/image_tools.py`：

```python
async def generate_image_asset(
    prompt: str,
    ...
    reference_images: list[str] | None = None,      # ← 参考图
    reference_asset_ids: list[str] | None = None,   # ← 参考资产
    character_ids: list[str] | None = None,         # ← 角色
    portrait_node_ids: list[str] | None = None,
    ...
)
```

**工具支持参考资产和角色，缺的是"用户怎么在对话里指定它们是哪几个"。**

现在的唯一路径是：用户用**文字描述** → Agent 调 `search_assets(query=…)` 去猜 →
猜错了用户再纠正。**用户想说"就用刚才那张图"是做不到的。**

---

## 二、"第几秒生成什么"：数据模型有，对话没有

### 我们的分镜 panel 早就有时间字段

`backend/app/services/ai/platform_templates_seed.py` L613-635 的分镜 schema：

```json
{
  "panel_number": 1,
  "image_prompt": "生图提示词",
  "video_prompt": "只描述可见动作、镜头运动和节奏的视频提示词",
  "duration_seconds": 4,                                  ← 秒数
  "camera_motion": "推近/拉远/摇镜/平移/跟拍/环绕/静止",   ← 运镜
  "shot_size": "远景/中景/特写/大宽格/窄格",
  "composition": "构图说明",
  "characters": ["角色"],
  "dialogue_bubbles": ["对白气泡"],
  "sound_effect": "音效字",
  "music_hint": "…",
  "generate_audio": false,
  "negative_prompt": "避免项"
}
```

而且提示词里**明确写了时间规则**（L599）：

> 「`duration_seconds` 必须是 **3-6 的整数**；特写通常 3 秒，中景 4 秒，
> 远景/大宽格 5-6 秒。」

### 分镜格已经能显示视频和时长

`frontend/src/pages/story/components/storyboard-parts.tsx` L329-367：

```
本格已生成视频 · {links.length}
  const duration = Number(metadata.duration)
  <video … />
  {duration > 0 ? <Tag>{duration}s</Tag> : null}
  <Button href="/video-gen?project_id=…&source_type=storyboard_panel&source_index=…">
    打开视频生成
  </Button>
```

**所以"某个镜头几秒、生成了什么视频"这件事，在分镜页是有的。**

### 缺的是：对话与时间轴没有连接

- 对话里说「第 5 秒改成特写」，**Agent 不知道你在说哪一格**
- 对话里说「这一格重做」，**没有"选中某格 → 对 Agent 说"的机制**
- `VideoGenerateRequest`（`videos.py` L104-127）是**一次一段**：
  只有 `prompt` + `duration` + `start_image`，**没有分段时间轴结构**

> **所以准确的说法是**：
> **不是"不支持按秒生成"，而是"支持到分镜格粒度，但对话无法触达这个粒度"。**

---

## 三、对照行业做法（来自本仓库调研）

| 能力 | 别人怎么做 | 出处 |
| --- | --- | --- |
| 对话加图 | **Claude Artifacts / ChatGPT Canvas** 直接把产物开在对话旁并可编辑 | `docs/research/2026-10-14_platform_comparison` |
| 指哪改哪 | Claude：「highlight the text you want changed… Claude makes the edit **where you marked it**, so you don't have to describe which section you mean」 | 同上 |
| 按格/按镜重生成 | **LTX Retake**：改光线/构图/表情，不重生成整镜 | 同上 |
| 分镜→成片 | **剪映 Hub**：批量生成 →「保存到资产主体」→「Agent 按分镜**引用我们准备好的资产**」→ 批量生成视频 | `docs/research/2026-10-15_ai_video_workflow_platforms` |
| 对话 vs 实况分离 | OpenMontage：「Chat tells you what the agent **said**. Backlot shows what the production is actually **doing**」 | `docs/research/2026-10-15_openmontage` |

**四条行业做法里，我们连最基础的"对话里给图"都没有。**

---

## 四、关于"智能体那的样式臃肿"

> 本节是**现象记录**，具体的界面诊断尚未逐屏做。`待评估`

已观察到的相关事实：

- `frontend/src/pages/agent/index.tsx` **单文件 4458 行**
- 页面同时承载：对话、执行轨迹、工具抽屉、长期记忆、线程列表、
  智能体配置、Skill 模板、工具授权、运行上下文 JSON……
- 实测时看到：顶部横幅 + 待确认卡片 + 执行轨迹 + 底部遥测条
  （Run/步骤/工具/耗时/LLM/Token/成本/缓存命中）**同屏堆叠**
- 工具结果被压成 `返回字段：…` 之后，**信息既没减少也没变清晰**

**但"臃肿"是主观判断，我没有做逐屏信息密度测量，不敢下定论。**
建议单独做一次 `/agent` 的界面审计（可用 `ylcraft-interaction-quality` 的检查清单）。

---

## 五、可以怎么补（三个层次，由小到大）

| 层次 | 做什么 | 依赖 |
| --- | --- | --- |
| **L1 最小** | `ChatRequest` 加 `attachment_asset_ids`；对话框加"引用素材"按钮（从素材库选，不一定要真的上传文件） | 后端加字段 + 前端选择器 |
| **L2 中间** | 对话里**选中某一格**再说话（把 `panel_number` 作为对话上下文传给 Agent） | L1 + 分镜页联动 |
| **L3 完整** | 对话里直接按秒操作（「第 5–8 秒改成…」）→ 落到 panel 修改 → 触发局部重生成 | L2 + `VideoGenerateRequest` 支持分段 |

**我的判断**：**L1 是地基**。没有"能引用素材"，L2/L3 都无从谈起。
而且 L1 恰好也是剪映 Hub「引用我们准备好的资产」那一步的前提。

---

## 六、实测对标：RunningHub 的「快捷创作」（一手，2026-10-15）

> 无需登录即可访问：`runninghub.cn` 首页「快捷创作」。
> 页面标题：**「AI生成器｜AI图片与视频一站式生成｜RunningHub」**

### 6.1 它的创作界面是**一个框**

实测到的完整控件清单（就这么少）：

| 元素 | 实测内容 |
| --- | --- |
| Tab | `Agent` / `图片` / `视频` |
| **上传** | **`选择文件` 按钮**（旁边有上传图标按钮） |
| 输入框 | 一个 prompt textbox |
| 模型 | `Seedream 5.0 Flash`（切换 tab 会变） |
| 参数 | `1:1 / 2k / JPEG` |
| 发送 | 按钮（空输入时 disabled） |
| 下方 | 模板库：「制作同款」+ 时长标签（`27s` / `11s` / `15s` / `6s`） |

**没有左侧栏、没有右侧栏、没有遥测条、没有轨迹面板。**

### 6.2 🔴 参考图上传是它的**核心能力**

实抓到的原文（HTML 原文，非推断）：

| 位置 | 原文 |
| --- | --- |
| 页面 meta 描述 | 「RunningHub AI生成器支持AI图片与视频生成，**可使用文字提示或参考图片创作**」 |
| 上传按钮 tooltip | 「**当前模型最多支持上传 10 张参考图**」（另一模型显示 **16 张**） |
| 模型说明 | 「**支持最多 10 张参考图，具备图层拆分功能**」 |
| 图标 tooltip | 「**参考图**」 |

**UI 细节（从 CSS 类名读出）**：
`qc-upload-row--tilted-expanded`、`qc-image-upload-stack`、
`upload-tilt-row-add--solo`（含 `--qc-upload-add-tilt-deg: -5deg`）
—— 参考图是**堆叠、倾斜排布的卡片**，是专门设计过的视觉。

> **这就是所有者指出的缺口**：
> 「别的（平台）是**在对话框里可以加图片**」—— **RunningHub 实测确认如此**，
> 而且参考图是**一等公民**（模型说明里直接标"最多 N 张"），不是附加功能。

### 6.3 与我们 Agent 页的对比

| 维度 | RunningHub 快捷创作 | 我们 `/agent` |
| --- | --- | --- |
| 输入区 | **一个框** | 输入框 + 顶部横幅 + 待确认卡 + 轨迹 + 遥测条 |
| 加参考图 | ✅ 最多 10–16 张，有专门视觉 | ❌ **完全没有** |
| 模型切换 | 一个下拉 | 有 |
| 参数 | 一行 `1:1 / 2k / JPEG` | 分散在确认卡片 |
| 模板 | 下方一行「制作同款」 | 无（或藏在别处） |
| 单文件行数 | — | `agent/index.tsx` **4458 行** |

**注意**：这**不是**说我们该把 Agent 页做成一个框 —— 我们的场景比它复杂得多。
但**"加参考图"这个能力，我们没有，它有**，而且是它的核心卖点。

---

## 七、关于注册平台

- **RunningHub 的关键界面无需登录即可看到**（快捷创作工作台可访问）。
  因此**本轮拿到了实测证据，没有注册**。
- 仍需登录才能看的：定价细节、API 文档、RHSTORY 内部、生成实际质量。
- **注册需要手机号/短信验证，我无法完成** —— 如果要看内部，
  需要所有者提供账号或自行注册后让我用浏览器读取。

---

## 八、待核实

| 项 | 状态 |
| --- | --- |
| 其他平台"对话框加图"的具体交互 | `待核实`（需实测或注册） |
| 我们前端是否已有可复用的素材选择器组件 | `待核实` |
| Agent 上下文里能否携带 panel 引用 | `待核实`（需读 `context` 的消费逻辑） |
| `/agent` 信息密度是否真的超标 | `待评估`（需逐屏审计） |
