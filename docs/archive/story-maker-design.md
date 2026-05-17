# Story Maker 完整设计方案
> 2026-05-03 初始设计

---

## 一、整体流程

```
用户输入主题
    ↓
LLM 生成故事结构（大纲 + 角色 + 分镜）
    ↓
┌─────────────────────────────────────────────┐
│  生成内容                                    │
│  ├── 故事大纲（plot_outline）                 │
│  ├── 风格设定（style_hint）                  │
│  ├── 角色列表（characters[]）                │
│  │   ├── name / role / description          │
│  │   ├── personality / appearance           │
│  │   └── costume_hint / voice_style         │
│  └── 分镜脚本（scenes[]）                    │
│      ├── scene_no / description             │
│      ├── dialogue / camera_hint             │
│      └── character_tags[]                   │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ 用户决策                                      │
│ 1. 每个角色 → 是否保存到角色库？              │
│ 2. 每个角色 → 生成多视图肖像？                │
│ 3. 每个分镜 → 生成配图？                      │
└─────────────────────────────────────────────┘
    ↓
执行选定操作
```

---

## 二、后端实现

### 2.1 新增 Service：`services/story/generator.py`

**输入**：`StoryPrompt(topic, style, num_scenes)`

**LLM Prompt 设计**（参考 ArcReel + LocalMiniDrama）：

```
你是一个专业的短剧剧本作家。
根据用户输入的主题，生成一个完整的短剧/漫剧故事结构。

风格：{style}（short_drama=都市短剧 / manga=二次元漫剧）
集数：1集，约{num_scenes}个分镜

请严格按以下JSON格式返回（只需JSON，不要其他文字）：
{
  "title": "故事标题",
  "plot_outline": "200字故事大纲",
  "style_hint": "视觉风格描述，用于AI生图",
  "characters": [
    {
      "name": "角色名",
      "role": "protagonist|antagonist|supporting|extra",
      "description": "角色定位简述",
      "personality": "性格特点",
      "appearance": "外貌描述（用于AI生图）",
      "costume_hint": "服装提示",
      "voice_style": "声音/音色建议"
    }
  ],
  "scenes": [
    {
      "scene_no": 1,
      "scene_title": "分镜标题",
      "description": "场景描述",
      "dialogue": "核心对白/旁白",
      "camera_hint": "镜头语言",
      "character_tags": ["角色1", "角色2"],
      "emotion": "情绪基调"
    }
  ],
  "music_hint": "配乐建议"
}
```

**输出**：`StoryGenerationResult`（包含大纲 + 角色 + 分镜）

### 2.2 新增 Service：`services/story/character_portrait_generator.py`

**功能**：为角色生成多视图肖像

**多视图方案**：
- 每个角色生成 4 张图（正面/3/4侧/背面），共用同一个 seed
- 通过调整 prompt 中的视角描述来实现一致性

**Prompt 模板**：
```
{appearance}, {costume_hint}
视角：{view_angle}（正面/四分之三侧脸/侧脸/背面）
风格：{style_hint}
确保角色外观高度一致
```

**存储**：生成的图片存入 `assets` 表，关联到角色

### 2.3 API 改造

**POST `/api/v1/story`** → 改名/重构为：
- `POST /api/v1/story/generate` — 故事生成（LLM）
- `POST /api/v1/story/characters` — 保存角色到库
- `POST /api/v1/story/portrait` — 为角色生成肖像
- `GET /api/v1/story/{story_id}` — 获取故事详情

**Story 数据模型**（新建 `db/models/story.py`）：
```python
class Story(SQLModel):
    id, title, topic, style, plot_outline, style_hint
    characters_json, scenes_json, music_hint
    status: generating|completed|failed
    created_at

class StoryCharacterPortrait(SQLModel):
    id, story_id, character_name, character_id  # 可选关联到角色库
    portrait_urls: list[str]  # 多视图 URLs
    prompt_used, created_at
```

---

## 三、前端改造

### 3.1 页面布局（三步骤）

```
┌──────────────────────────────────────────────────────┐
│ Step 1: 输入创作主题                                  │
│ ┌────────────────────────────────────────────────┐  │
│ │  主题输入框                                      │  │
│ │  风格选择  集数选择                              │  │
│ │  [开始创作]                                     │  │
│ └────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────┤
│ Step 2: 生成结果（LLM输出展示）                       │
│  ┌────────────┐  ┌─────────────────────────────┐    │
│  │ 角色卡片    │  │ 分镜脚本列表                 │    │
│  │ [保存角色] │  │ 第1场: ... [生图]           │    │
│  │ [生肖像]   │  │ 第2场: ... [生图]           │    │
│  │ [多视图]   │  │ ...                         │    │
│  └────────────┘  └─────────────────────────────┘    │
├──────────────────────────────────────────────────────┤
│ Step 3: 素材确认 & 导出                              │
│  角色库预览  分镜配图  导出剪映草稿                   │
└──────────────────────────────────────────────────────┘
```

### 3.2 角色卡片交互

- **保存到角色库**：一键保存，关联 story_id
- **生成肖像**（单角色）：
  - 点击 → 调用 portrait API → 显示多视图（4张）
  - 用户可选择其中一张作为主立绘
- **生成多视图**：前端展示 4 个视角的缩略图，点击放大

### 3.3 分镜脚本展示

- 每个分镜卡片显示：序号、场景描述、对白、镜头语言
- **[生配图]** 按钮：调用生图 API，将 description 作为 prompt
- **[角色一致]**：用已生成的角色的 portrait_url 作为参考图

---

## 四、角色一致性策略

参考 ArcReel 的方案：

1. **角色冻结（is_frozen）**：用户确认角色外观后，可冻结 appearance，冻结后不允许修改
2. **Seed 一致性**：生成角色立绘时记录 seed，后续生成分镜图时传入 seed 以保持一致
3. **角色 ID 注入**：分镜 prompt 中注入角色 appearance 描述作为参考

---

## 五、技术要点

### 5.1 LLM 调用
- 通过 `BackendManager.chat()` 调用 Doubao LLM
- 使用 `structured_output()` 获取结构化 JSON
- 超时处理：60s，超时返回错误提示用户重试

### 5.2 图片生成一致性
- 使用 `seed` 参数（如果 provider 支持）
- 或者将角色 appearance 作为 negative prompt 的约束
- 多视图通过调整 prompt 中的视角词实现

### 5.3 任务队列
- 故事生成为同步调用（LLM 响应时间可控）
- 肖像生成为异步任务（批量生成多图）

---

## 六、实现顺序

1. **[Step 1]** `services/story/generator.py` + `/api/v1/story/generate` 后端
2. **[Step 2]** 前端 Story Maker 页面重构，显示生成结果
3. **[Step 3]** 角色保存 API + 前端"保存角色"按钮
4. **[Step 4]** 角色肖像生成 API + 前端多视图展示
5. **[Step 5]** 分镜配图生成 + 角色一致性注入
