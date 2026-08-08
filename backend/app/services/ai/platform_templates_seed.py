"""
平台模板种子数据

基于 yiliu/yiliu 的 platform_templates.yaml，适配 YLCraft 架构后引入。
每个模板包含:
- outline_template: LLM 将 topic 展开为结构化大纲的 system prompt
- image_template: 将大纲每页转换为生图提示词的 prompt 模板
- page_structure: 机器可读的默认页面结构(JSONB)，驱动空白大纲生成+前端渲染

变量说明:
- {topic}: 用户输入的主题
- {page_structure}: 平台默认页面结构（JSON 文本）
- {page_content}: 当前页的内容描述
- {page_type}: 页面类型（如 [封面]/[内容]/[总结]）
- {full_outline}: 完整大纲（供 image_template 参考保持风格一致）
- {user_topic}: 用户原始输入
"""

# 小红书 - 竖版 3:4，清新简约风格
_XHS_OUTLINE = """你是一个小红书内容创作专家。用户会给你一个需求以及说明，你需要生成一个适合小红书的图文内容大纲。

用户的需求以及说明：{topic}
平台默认页面结构参考：{page_structure}

核心规则（必须严格遵守）：
1. 【标题】必须是吸引人的、有创意的分段标题，绝对不能直接复制用户输入的原文，要重新创作一个有吸引力的标题
2. 【文案】必须是完整的图文配文，不能是用户输入的原文，要有小红书风格的语气和话题标签
3. 第一页必须是吸引人的封面页面（[封面]类型），包含封面视觉描述
4. 内容控制在 6-12 页（包含封面）
5. 每页内容简洁有力，适合配图展示
6. 使用小红书风格的语言（亲切、有趣、实用）
7. 可以适当使用 emoji 增加趣味性
8. 内容要有实用价值，能解决用户问题或提供有用信息
9. 最后一页必须是总结或行动号召（[总结]类型）

输出格式（严格遵守）：
- 首先是【标题】：开头（注意：是创意标题，不是用户原文！）
- 接下来是【文案】：开头
- 然后是多个图片说明词，每张图片使用【图片说明词】：开头，用 --- 标记分隔每一页
- 页面类型使用规则：
  * 第一页必须使用 [封面] 类型
  * 中间页面使用 [内容] 类型
  * 最后一页必须使用 [总结] 类型
- 后面是该页的具体内容描述，要具体、详细，方便后续生成图片
- 避免在内容中使用 | 竖线符号"""

_XHS_IMAGE = """请生成一张小红书风格的图文内容图片。
注意：不要带有任何小红书的logo或水印标志。

页面内容：{page_content}
页面类型：{page_type}
设计：清新风格3:4竖版
主题：{user_topic}"""

# 抖音 - 竖版 9:16，潮流酷炫风格
_DOUYIN_OUTLINE = """你是一个抖音内容创作专家。用户会给你一个需求以及说明，你需要生成一个适合抖音的图文内容大纲。

用户的需求以及说明：{topic}
平台默认页面结构参考：{page_structure}

核心规则（必须严格遵守）：
1. 【标题】必须是吸引人的、有创意的分段标题，绝对不能直接复制用户输入的原文，要重新创作一个有吸引力的标题
2. 【文案】必须是完整的图文配文，不能是用户输入的原文，要有抖音风格的语气和话题标签
3. 第一页必须是吸引人的封面页面（[封面]类型），包含封面视觉描述
4. 内容控制在 3-8 页（包含封面）
5. 每页内容简洁有力，适合短视频图文展示
6. 使用抖音风格的语言（潮流、酷炫、有节奏感）
7. 可以适当使用 emoji 和热门话题标签
8. 内容要有冲击力，能快速抓住用户注意力
9. 最后一页必须是总结或行动号召（[总结]类型）

输出格式（严格遵守）：
- 首先是【标题】：开头（注意：是创意标题，不是用户原文！）
- 接下来是【文案】：开头
- 然后是多个图片说明词，每张图片使用【图片说明词】：开头，用 --- 标记分隔每一页
- 页面类型使用规则：
  * 第一页必须使用 [封面] 类型
  * 中间页面使用 [内容] 类型
  * 最后一页必须使用 [总结] 类型
- 后面是该页的具体内容描述，要具体、详细，方便后续生成图片
- 避免在内容中使用 | 竖线符号"""

_DOUYIN_IMAGE = """请生成一张抖音风格的图文内容图片。
注意：不要带有任何抖音的logo或水印标志。

页面内容：{page_content}
页面类型：{page_type}
设计：潮流酷炫风格9:16竖版
主题：{user_topic}"""

# 微信公众号 - 横版 16:9，专业正式风格
_WECHAT_OUTLINE = """你是一个微信公众号内容创作专家。用户会给你一个需求以及说明，你需要生成一个适合微信公众号的图文内容大纲。

用户的需求以及说明：{topic}
平台默认页面结构参考：{page_structure}

核心规则（必须严格遵守）：
1. 【标题】必须是吸引人的、有创意的分段标题，绝对不能直接复制用户输入的原文，要重新创作一个有吸引力的标题
2. 【文案】必须是完整的图文配文，不能是用户输入的原文，要有公众号风格的语气和话题标签
3. 第一页必须是标题页面（[标题]类型），包含文章主题概述
4. 内容控制在 5-20 页（包含标题页）
5. 每页内容要有深度，适合深度阅读
6. 使用公众号风格的语言（专业、权威、有价值）
7. 内容要有结构，逻辑清晰
8. 提供有价值的信息和观点
9. 最后一页必须是总结或行动号召（[总结]类型）

输出格式（严格遵守）：
- 首先是【标题】：开头（注意：是创意标题，不是用户原文！）
- 接下来是【文案】：开头
- 然后是多个图片说明词，每张图片使用【图片说明词】：开头，用 --- 标记分隔每一页
- 页面类型使用规则：
  * 第一页必须使用 [标题] 类型
  * 中间页面使用 [内容] 类型
  * 最后一页必须使用 [总结] 类型
- 后面是该页的具体内容描述，要具体、详细，方便后续生成图片
- 避免在内容中使用 | 竖线符号"""

_WECHAT_IMAGE = """请生成一张微信公众号风格的图文内容图片。
注意：不要带有任何微信的logo或水印标志。

页面内容：{page_content}
页面类型：{page_type}
设计：专业正式风格16:9横版
主题：{user_topic}"""

# 头条号 - 横版 16:9，资讯新闻风格
_TOUTIAO_OUTLINE = """你是一个头条号内容创作专家。用户会给你一个需求以及说明，你需要生成一个适合头条号的图文内容大纲。

用户的需求以及说明：{topic}
平台默认页面结构参考：{page_structure}

核心规则（必须严格遵守）：
1. 【标题】必须是吸引人的、有创意的分段标题，绝对不能直接复制用户输入的原文，要重新创作一个有吸引力的标题
2. 【文案】必须是完整的图文配文，不能是用户输入的原文，要有头条风格的语气和话题标签
3. 第一页必须是标题页面（[标题]类型），包含文章主题概述
4. 内容控制在 5-15 页（包含标题页）
5. 每页内容要有信息量，适合快速阅读
6. 使用头条风格的语言（新闻资讯风格、客观中立）
7. 内容要有吸引力，能抓住用户眼球
8. 提供有价值的信息和观点
9. 最后一页必须是结尾总结（[结尾]类型）

输出格式（严格遵守）：
- 首先是【标题】：开头（注意：是创意标题，不是用户原文！）
- 接下来是【文案】：开头
- 然后是多个图片说明词，每张图片使用【图片说明词】：开头，用 --- 标记分隔每一页
- 页面类型使用规则：
  * 第一页必须使用 [标题] 类型
  * 中间页面使用 [内容] 类型
  * 最后一页必须使用 [结尾] 类型
- 后面是该页的具体内容描述，要具体、详细，方便后续生成图片
- 避免在内容中使用 | 竖线符号"""

_TOUTIAO_IMAGE = """请生成一张头条号风格的图文内容图片。
注意：不要带有任何头条的logo或水印标志。

页面内容：{page_content}
页面类型：{page_type}
设计：资讯新闻风格16:9横版
主题：{user_topic}"""

PLATFORM_TEMPLATE_SEEDS = [
    {
        "platform": "xiaohongshu",
        "name": "小红书",
        "outline_template": _XHS_OUTLINE,
        "image_template": _XHS_IMAGE,
        "page_structure": {
            "default_pages": [
                {"type": "封面"},
                {"type": "内容"},
                {"type": "内容"},
                {"type": "内容"},
                {"type": "内容"},
                {"type": "总结"}
            ]
        },
        "video_template": None,
        "default_size": "768x1024",
        "is_active": True,
        "sort_order": 1,
        "id": "9494350c-5819-4690-acb6-fc57a1e2d2d9"
    },
    {
        "platform": "douyin",
        "name": "抖音",
        "outline_template": _DOUYIN_OUTLINE,
        "image_template": _DOUYIN_IMAGE,
        "page_structure": {
            "default_pages": [
                {"type": "封面"},
                {"type": "内容"},
                {"type": "内容"},
                {"type": "总结"}
            ]
        },
        "video_template": None,
        "default_size": "1080x1920",
        "is_active": True,
        "sort_order": 2,
        "id": "2683f607-8990-4cb4-9cc3-75e7c4f4a66a"
    },
    {
        "platform": "wechat",
        "name": "微信",
        "outline_template": _WECHAT_OUTLINE,
        "image_template": _WECHAT_IMAGE,
        "page_structure": {
            "default_pages": [
                {"type": "标题"},
                {"type": "引言"},
                {"type": "正文"},
                {"type": "案例"},
                {"type": "正文"},
                {"type": "总结"}
            ]
        },
        "video_template": None,
        "default_size": "1280x720",
        "is_active": True,
        "sort_order": 3,
        "id": "353cedf4-f231-4ab8-a3fc-e075a9de9624"
    },
    {
        "platform": "toutiao",
        "name": "头条",
        "outline_template": _TOUTIAO_OUTLINE,
        "image_template": _TOUTIAO_IMAGE,
        "page_structure": {
            "default_pages": [
                {"type": "标题"},
                {"type": "导语"},
                {"type": "正文"},
                {"type": "图片说明"},
                {"type": "结尾"}
            ]
        },
        "video_template": None,
        "default_size": "1280x720",
        "is_active": True,
        "sort_order": 4,
        "id": "25396ae1-8180-4356-9dc3-6e7f1c88bdf4"
    }
]


_CREATIVE_SYSTEM = """你是资深网文主编、漫画脚本统筹和长篇连载策划。
你必须输出严格 JSON，不要输出 Markdown、解释、代码块或 JSON 以外的文字。
规划要服务后续逐话正文创作和漫画分镜生成，必须具体、可执行、前后连续。"""


_CREATIVE_OUTLINE = """请根据用户创意生成一份长篇小说/漫画/短剧项目的故事大纲 JSON。

项目类型：{project_type}
项目标题：{project_title}
用户创意：
{idea}

参考小说章节节选：
{source_sample}

输出 JSON 对象，字段必须包含：
{
  "title": "作品标题",
  "genre": ["题材1", "题材2"],
  "logline": "一句话卖点",
  "target_reader": "目标读者",
  "tone": "叙事气质",
  "worldview": "世界观与规则",
  "main_conflict": "主线冲突",
  "themes": ["主题1", "主题2"],
  "characters": [
    {
      "name": "角色名",
      "role": "定位",
      "age_range": "年龄段",
      "appearance": "脸型、发型、体态、辨识度外貌",
      "costume_hint": "服装、配色、标志物",
      "personality": "性格",
      "background": "人物前史与欲望/创伤来源",
      "goal": "目标",
      "arc": "成长弧光",
      "visual_tags": ["稳定视觉标签1", "稳定视觉标签2"],
      "voice": "说话方式、口头禅、台词气质",
      "image_prompt": "可直接用于生成角色设定图的完整提示词，包含年龄、脸型、发型、服装、气质、构图、风格",
      "negative_prompt": "不希望出现在角色图里的元素",
      "portrait_asset_id": "",
      "reference_asset_ids": []
    }
  ],
  "relationship_map": "主要人物关系",
  "premise": "作品核心前提，说明主角为什么非行动不可",
  "selling_points": ["强卖点1", "强卖点2", "强卖点3"],
  "audience_emotion": "希望读者/观众持续获得的情绪体验",
  "narrative_rules": ["创作规则1", "反套路边界1", "爽点兑现规则1"],
  "locations": [
    {"name": "核心场景名", "role": "叙事功能", "visual_description": "场景视觉描述", "mood": "氛围", "reusable_asset_note": "可复用素材说明"}
  ],
  "story_arc": {
    "beginning": "开局",
    "middle": "中段升级",
    "climax": "高潮",
    "ending_direction": "结局方向"
  },
  "visual_style": "适合漫画化和短视频化的视觉风格",
  "image_style_prompt": "统一生图风格提示词，供角色图、场景图、分镜图复用",
  "production_notes": ["后续生成脚本/分镜/图片时必须遵守的制作约束"]
}

要求：
1. 大纲要服务后续章节规划、短剧脚本、漫画分镜和素材库管理。
2. 角色 image_prompt 必须能直接送入生图功能，用来保持人物形象一致。
3. 如果还没有素材库图片，portrait_asset_id 留空字符串，reference_asset_ids 留空数组。"""

_CREATIVE_CHAPTER_PLAN = """请根据下面的故事大纲，生成 {chapter_count} 章/集的连续规划 JSON。

故事大纲：
{outline_json}

要求：
1. 每章要推动主线，不要只写氛围。
2. 每章都要有明确目标、冲突、关键事件和结尾钩子。
3. 角色成长和关系变化要连续。
4. 输出严格 JSON，不要 Markdown。

输出格式：
{
  "chapter_count": {chapter_count},
  "chapters": [
    {
      "chapter_number": 1,
      "title": "章节标题",
      "goal": "本章叙事目标",
      "conflict": "本章核心冲突",
      "key_events": ["事件1", "事件2"],
      "character_focus": ["角色名"],
      "ending_hook": "结尾钩子",
      "status": "planned"
    }
  ]
}"""

_CREATIVE_CHAPTER_OUTLINE = """请根据故事大纲和章节规划，生成第 {chapter_number} 章/集的单话细纲 JSON。

故事大纲：
{outline_json}

章节规划：
{chapter_plan_json}

当前章节：
{current_chapter_json}

前文上下文：
{previous_context}

要求：
1. 单话细纲要比章节规划更细，能直接服务后续小说正文、短剧脚本和分镜。
2. scenes 需要有明确场景目标、冲突推进、动作、情绪转折和可生图 image_prompt。
3. key_dialogues 写关键台词或台词方向，不要写成空泛总结。
4. foreshadowing 和 continuity_notes 要帮助后续章节保持连续。
5. 输出严格 JSON，不要 Markdown。

输出格式：
{
  "chapter_number": {chapter_number},
  "title": "单话标题",
  "summary": "本章完整摘要",
  "objective": "本章叙事目标",
  "scenes": [
    {
      "scene_number": 1,
      "title": "场景标题",
      "location": "地点",
      "characters": ["角色"],
      "objective": "场景目标",
      "conflict": "场景冲突",
      "action": "具体剧情动作",
      "emotional_turn": "情绪变化",
      "image_prompt": "可直接用于生成场景概念图的提示词"
    }
  ],
  "key_dialogues": ["关键台词或台词方向"],
  "foreshadowing": ["伏笔"],
  "ending_hook": "结尾钩子",
  "continuity_notes": ["连续性备注"]
}"""

_CREATIVE_NOVEL_BODY = """请根据单话细纲生成第 {chapter_number} 章小说正文 JSON。

故事大纲：
{outline_json}

章节规划：
{chapter_plan_json}

当前单话细纲：
{chapter_outline_json}

前文上下文：
{previous_context}

要求：
1. content 字段输出完整小说正文，不要只写摘要。
2. 正文要遵守大纲中的人物设定、视觉风格、世界规则和连续性备注。
3. 保持网文/短剧改编友好的节奏：开头有钩子，中段有推进，结尾留悬念。
4. 可以有对白、动作和心理描写，但不要输出 Markdown 标题。
5. 输出严格 JSON，不要 Markdown。

输出格式：
{
  "chapter_number": {chapter_number},
  "title": "章节标题",
  "content": "完整小说正文",
  "word_count": 0,
  "continuity_notes": ["给下一章或拆页使用的连续性备注"]
}"""

_CREATIVE_COMIC_PAGES = """请根据分镜草稿整理成适合漫画生成的 {page_count} 页漫画脚本 JSON。

项目标题：{project_title}
章节：第 {chapter_number} 章
视觉风格：{visual_style}
统一生图风格提示：{image_style_prompt}

分镜草稿：
{storyboard_json}

要求：
1. pages 必须正好 {page_count} 页，page_number 从 1 连续递增。
2. 每页 content 使用【第1格】这样的分格标记，建议每页 3-6 格。
3. 每页应承接 storyboard panels，不要凭空改剧情；可以把多个 panel 合并成一页，也可以把复杂 panel 拆成多格。
4. 每格写清角色、动作、画面、对白气泡、音效和镜头节奏。
5. 每页 image_prompt 是该页关键视觉提示，能直接送到生图。
6. 保持角色外观和视觉风格一致。
7. 输出严格 JSON，不要 Markdown。

输出格式：
{
  "episode_number": {chapter_number},
  "chapter_number": {chapter_number},
  "title": "漫画拆页标题",
  "page_count": {page_count},
  "visual_style": "统一视觉风格",
  "pages": [
    {
      "page_number": 1,
      "title": "本页标题",
      "content": "第1页：\\n【第1格】...\\n【第2格】...",
      "image_prompt": "本页关键画面提示词"
    }
  ]
}"""

_CREATIVE_SCRIPT = """请把指定章节改写成短剧单集脚本 JSON。

故事大纲：
{outline_json}

章节规划：
{chapter_plan_json}

当前章节：
{current_chapter_json}

要求：
1. 开头 5 秒必须有钩子。
2. 场景适合 60-120 秒竖屏短剧。
3. 每个 scene 都要给出可用于 AI 生图的 image_prompt。
4. 输出严格 JSON。

输出格式：
{
  "episode_number": {chapter_number},
  "title": "单集标题",
  "duration_target_seconds": 90,
  "hook": "开头钩子",
  "scenes": [
    {
      "scene_number": 1,
      "location": "地点",
      "characters": ["角色"],
      "action": "动作与剧情",
      "dialogue": [{"character": "角色", "line": "台词"}],
      "camera_hint": "镜头建议",
      "emotion": "情绪",
      "image_prompt": "画面提示词"
    }
  ],
  "ending_hook": "结尾钩子"
}"""

_CREATIVE_STORYBOARD = """请根据短剧脚本生成漫画/视频分镜 JSON。

视觉制作档案：
{visual_style}

统一生图风格提示：
{image_style_prompt}

角色视觉档案：
{character_bible_json}

场景视觉档案：
{locations_json}

项目参考素材：
{reference_assets_json}

故事大纲：
{outline_json}

脚本：
{script_json}

要求：
1. 每个 panel 都要能独立用于 AI 图片生成，不能只写剧情摘要。
2. 每个 image_prompt 必须写成镜头级漫画生图提示词，包含：角色身份、角色外貌、服装、地点道具、动作、表情、景别、镜头角度、构图、光线色调、氛围、漫画风格、画面重点和一致性要求。
3. video_prompt 与 image_prompt 分开写：只描述首帧之后的动作、镜头运动、节奏和情绪变化，不能复制静态外貌清单，也不能写字幕、分镜编号或模型参数。
4. duration_seconds 必须是 3-6 的整数；特写通常 3 秒，中景 4 秒，远景/大宽格 5-6 秒。camera_motion 只使用 推近/拉远/摇镜/平移/跟拍/环绕/静止 之一。
5. generate_audio 默认 false；只在需要原生环境声或音乐时设 true，并在 music_hint 写简短建议。
6. image_prompt 必须复用角色视觉档案，不允许只写“某人醒来”“递合同”等剧情短句。
7. panels 要覆盖完整剧情节拍，每场至少 2-4 个 panel，远景/中景/特写/大宽格交替，避免连续同景别。
8. dialogue_bubbles 写本格可见对白气泡，sound_effect 写拟声词或环境声，negative_prompt 写需要避免的画面问题。
9. 如果项目参考素材里有 character/background/style/reference，请把参考意图写入 image_prompt。
10. 保持角色外观、服装、场景和视觉风格一致。
11. 输出严格 JSON。

输出格式：
{
  "episode_number": {episode_number},
  "title": "分镜标题",
  "visual_style": "统一视觉风格",
  "panels": [
    {
      "panel_number": 1,
      "source_scene_number": 1,
      "image_prompt": "生图提示词",
      "video_prompt": "只描述可见动作、镜头运动和节奏的视频提示词",
      "duration_seconds": 4,
      "camera_hint": "镜头",
      "camera_motion": "推近/拉远/摇镜/平移/跟拍/环绕/静止",
      "shot_size": "远景/中景/特写/大宽格/窄格",
      "composition": "构图说明",
      "characters": ["角色"],
      "action": "动作",
      "emotion": "情绪",
      "dialogue_bubbles": ["对白气泡"],
      "sound_effect": "音效字",
      "music_hint": "可选的环境声或配乐建议",
      "generate_audio": false,
      "negative_prompt": "避免项",
      "notes": "备注"
    }
  ]
}"""

_WRITER_ROOM_SCENE_BEATS = """请作为导演，把第 {chapter_number} 章拆成可写正文的场景节拍 JSON。
故事大纲：{outline_json}
章节规划：{chapter_plan_json}
当前章节细纲：{chapter_outline_json}
前文上下文：{previous_context}
要求：场景必须有目标、阻碍、冲突压力、动作节拍、潜台词、感官锚点和转折。输出严格 JSON。"""

_WRITER_ROOM_CHARACTER_REHEARSAL = """请作为角色演绎室，让第 {chapter_number} 章关键角色按自己的欲望、恐惧、已知信息和隐瞒信息先演一遍。
故事大纲：{outline_json}
章节细纲：{chapter_outline_json}
场景节拍：{scene_beats_json}
要求：输出角色反应、可用冲突、潜台词和可能对白。输出严格 JSON。"""

_WRITER_ROOM_PROSE_DRAFT = """请根据场景节拍和角色演绎，写第 {chapter_number} 章小说正文初稿 JSON。
故事大纲：{outline_json}
章节细纲：{chapter_outline_json}
场景节拍：{scene_beats_json}
角色演绎：{character_rehearsal_json}
要求：content 是完整正文，目标 3000-4500 中文字符，多写具体动作、物件互动、环境细节和潜台词，少写泛化情绪解释。输出严格 JSON。"""

_WRITER_ROOM_HUMANIZE = """请作为人味润色编辑，重写第 {chapter_number} 章正文并输出 JSON。
章节细纲：{chapter_outline_json}
待润色正文：{source_text}
用户额外要求：{instruction}
要求：保留剧情事实和角色关系；删掉解释性废话；把直接情绪改成动作、停顿、视线、物件互动和对白潜台词；改掉重复句式和万能比喻。输出完整正文 JSON。"""

_WRITER_ROOM_REVIEW = """请作为网文主编审稿，指出第 {chapter_number} 章正文里不像真人作者的地方。
章节细纲：{chapter_outline_json}
待审稿正文：{source_text}
要求：问题必须具体到段落、场景或句式位置，覆盖节奏、逻辑、角色声音、情绪连续性、爽点/钩子、AI腔，并给出 quality_tags、ai_smell_checks 和可执行 rewrite_instruction。输出严格 JSON。"""

_WRITER_ROOM_REWRITE = """请作为重写作者，根据审稿意见重写第 {chapter_number} 章正文。
章节细纲：{chapter_outline_json}
待重写正文：{source_text}
局部选段（如果为空则整章重写）：{selected_text}
审稿意见：{prose_review_json}
用户额外要求：{instruction}
要求：不擅自改主线事实，优先修复 high/medium 问题；如果有局部选段，只重写选段相关段落并替换回全文；输出完整正文 JSON。"""


def _writer_room_seed(
    *,
    platform: str,
    name: str,
    stage: str,
    description: str,
    template: str,
    sort_order: int,
    template_id: str,
):
    return {
        "platform": platform,
        "name": name,
        "template_scope": "creative_project",
        "template_stage": stage,
        "description": description,
        "system_template": _CREATIVE_SYSTEM,
        "outline_template": template,
        "image_template": "",
        "page_structure": {},
        "variables": {
            "project_title": "项目标题",
            "project_type": "项目类型",
            "chapter_number": "当前章节",
            "outline_json": "故事大纲 JSON",
            "chapter_plan_json": "章节规划 JSON",
            "current_chapter_json": "当前章节规划 JSON",
            "chapter_outline_json": "章节细纲 JSON",
            "scene_beats_json": "场景节拍 JSON",
            "character_rehearsal_json": "角色演绎 JSON",
            "source_text": "源正文文本",
            "selected_text": "局部选段文本",
            "source_json": "源内容 JSON",
            "prose_review_json": "审稿意见 JSON",
            "previous_context": "前文上下文",
            "instruction": "用户额外要求",
        },
        "video_template": None,
        "default_size": "1024x1024",
        "is_active": True,
        "sort_order": sort_order,
        "id": template_id,
    }

CREATIVE_PROJECT_TEMPLATE_SEEDS = [
    {
        "platform": "creative_outline",
        "name": "创作项目：故事大纲",
        "template_scope": "creative_project",
        "template_stage": "outline",
        "description": "从创意或小说节选生成项目级故事大纲、角色视觉设定和制作约束。",
        "system_template": _CREATIVE_SYSTEM,
        "outline_template": _CREATIVE_OUTLINE,
        "image_template": "",
        "page_structure": {},
        "variables": {
            "project_title": "项目标题",
            "project_type": "项目类型",
            "idea": "用户创意或改编说明",
            "source_sample": "小说章节节选，可为空",
        },
        "video_template": None,
        "default_size": "1024x1024",
        "is_active": True,
        "sort_order": 101,
        "id": "ecdc6be0-3f96-4f1b-8d39-a8253da68f45",
    },
    {
        "platform": "creative_chapter_plan",
        "name": "创作项目：章节规划",
        "template_scope": "creative_project",
        "template_stage": "chapter_plan",
        "description": "基于大纲拆出连续章节/集规划，保证主线、冲突、钩子和角色变化连续。",
        "system_template": _CREATIVE_SYSTEM,
        "outline_template": _CREATIVE_CHAPTER_PLAN,
        "image_template": "",
        "page_structure": {},
        "variables": {
            "chapter_count": "目标章节/集数",
            "outline_json": "故事大纲 JSON",
        },
        "video_template": None,
        "default_size": "1024x1024",
        "is_active": True,
        "sort_order": 102,
        "id": "c748fa0f-8e4f-46cc-9680-2b6f945f6995",
    },
    {
        "platform": "creative_chapter_outline",
        "name": "创作项目：单话细纲",
        "template_scope": "creative_project",
        "template_stage": "chapter_outline",
        "description": "把某一章/集扩展为可执行细纲，包含场景、关键台词、伏笔和连续性备注。",
        "system_template": _CREATIVE_SYSTEM,
        "outline_template": _CREATIVE_CHAPTER_OUTLINE,
        "image_template": "",
        "page_structure": {},
        "variables": {
            "outline_json": "故事大纲 JSON",
            "chapter_plan_json": "章节规划 JSON",
            "current_chapter_json": "当前章节规划 JSON",
            "chapter_number": "当前章节/集数",
            "previous_context": "前文上下文摘要",
        },
        "video_template": None,
        "default_size": "1024x1024",
        "is_active": True,
        "sort_order": 103,
        "id": "6fb43888-8c5e-432d-9e63-a6c4915f7081",
    },
    {
        "platform": "creative_novel_body",
        "name": "创作项目：章节正文",
        "template_scope": "creative_project",
        "template_stage": "novel_body",
        "description": "根据单话细纲生成章节正文，后续可继续拆成漫画页或短剧脚本。",
        "system_template": _CREATIVE_SYSTEM,
        "outline_template": _CREATIVE_NOVEL_BODY,
        "image_template": "",
        "page_structure": {},
        "variables": {
            "outline_json": "故事大纲 JSON",
            "chapter_plan_json": "章节规划 JSON",
            "chapter_outline_json": "单话细纲 JSON",
            "chapter_number": "当前章节/集数",
            "previous_context": "前文上下文摘要",
        },
        "video_template": None,
        "default_size": "1024x1024",
        "is_active": True,
        "sort_order": 104,
        "id": "a64999af-87a1-4ddf-a9c7-402cd06f4eb3",
    },
    {
        "platform": "creative_comic_pages",
        "name": "创作项目：漫画拆页",
        "template_scope": "creative_project",
        "template_stage": "comic_pages",
        "description": "把章节正文拆成漫画页脚本，每页包含分格文本和可生图提示词。",
        "system_template": _CREATIVE_SYSTEM,
        "outline_template": _CREATIVE_COMIC_PAGES,
        "image_template": "",
        "page_structure": {},
        "variables": {
            "project_title": "项目标题",
            "chapter_number": "当前章节/集数",
            "page_count": "目标页数",
            "visual_style": "统一视觉风格",
            "image_style_prompt": "统一生图风格提示词",
            "storyboard_json": "分镜草稿 JSON",
            "storyboard_text": "分镜草稿文本",
            "source_content_json": "源分镜内容 JSON",
            "source_content_text": "源分镜文本",
        },
        "video_template": None,
        "default_size": "1024x1024",
        "is_active": True,
        "sort_order": 105,
        "id": "00af4782-d974-41e9-aa55-50d17f3d7476",
    },
    {
        "platform": "creative_script",
        "name": "创作项目：短剧脚本",
        "template_scope": "creative_project",
        "template_stage": "script",
        "description": "把选定章节改写为短剧单集脚本，并沉淀场景级生图提示词。",
        "system_template": _CREATIVE_SYSTEM,
        "outline_template": _CREATIVE_SCRIPT,
        "image_template": "",
        "page_structure": {},
        "variables": {
            "outline_json": "故事大纲 JSON",
            "chapter_plan_json": "章节规划 JSON",
            "current_chapter_json": "当前章节规划 JSON",
            "chapter_number": "当前章节/集数",
        },
        "video_template": None,
        "default_size": "1024x1024",
        "is_active": True,
        "sort_order": 106,
        "id": "4d33e111-ad15-47e5-bd8d-750c278d7f28",
    },
    {
        "platform": "creative_storyboard",
        "name": "创作项目：分镜草稿",
        "template_scope": "creative_project",
        "template_stage": "storyboard",
        "description": "把脚本拆成漫画/视频分镜，并生成每格可直接生图的 prompt。",
        "system_template": _CREATIVE_SYSTEM,
        "outline_template": _CREATIVE_STORYBOARD,
        "image_template": "",
        "page_structure": {},
        "variables": {
            "visual_style": "统一视觉风格",
            "image_style_prompt": "统一生图风格提示",
            "character_bible_json": "角色视觉档案 JSON",
            "locations_json": "场景视觉档案 JSON",
            "reference_assets_json": "项目参考素材 JSON",
            "visual_context": "合并后的视觉制作档案",
            "outline_json": "故事大纲 JSON",
            "script_json": "短剧脚本 JSON",
            "episode_number": "当前集数",
        },
        "video_template": None,
        "default_size": "1024x1024",
        "is_active": True,
        "sort_order": 107,
        "id": "b2796b4e-0e0c-452d-a78f-776953444926",
    },
    _writer_room_seed(
        platform="writer_room_scene_beats",
        name="写作室：导演场景节拍",
        stage="scene_beats",
        description="把章节细纲拆成可写正文的戏剧节拍、冲突压力和感官锚点。",
        template=_WRITER_ROOM_SCENE_BEATS,
        sort_order=121,
        template_id="5d7c1d7a-0609-4d52-a39b-3a1c0bcf7121",
    ),
    _writer_room_seed(
        platform="writer_room_character_rehearsal",
        name="写作室：角色演绎",
        stage="character_rehearsal",
        description="让角色从自身欲望、恐惧和隐瞒信息出发表演，沉淀潜台词和对白方向。",
        template=_WRITER_ROOM_CHARACTER_REHEARSAL,
        sort_order=122,
        template_id="0d1b2c89-8b94-4cb0-9858-5d7a422b0d2d",
    ),
    _writer_room_seed(
        platform="writer_room_prose_draft",
        name="写作室：正文初稿",
        stage="prose_draft",
        description="基于场景节拍和角色演绎生成完整正文初稿。",
        template=_WRITER_ROOM_PROSE_DRAFT,
        sort_order=123,
        template_id="3e9d8c01-0a9f-4b20-b6f1-12af3ae7422e",
    ),
    _writer_room_seed(
        platform="writer_room_humanize",
        name="写作室：人味润色",
        stage="prose_humanized",
        description="把 AI 腔正文重写成更自然的动作、对白、节奏和潜台词。",
        template=_WRITER_ROOM_HUMANIZE,
        sort_order=124,
        template_id="e8e7fc3f-9a2d-4a0c-9f7f-c01082ab3d66",
    ),
    _writer_room_seed(
        platform="writer_room_review",
        name="写作室：网文主编审稿",
        stage="prose_review",
        description="按节奏、逻辑、角色声音、情绪连续性和 AI 腔给出可执行审稿意见。",
        template=_WRITER_ROOM_REVIEW,
        sort_order=125,
        template_id="94ce0b13-89a7-42dd-950f-7834de38c932",
    ),
    _writer_room_seed(
        platform="writer_room_rewrite",
        name="写作室：定向重写",
        stage="prose_rewrite",
        description="根据审稿意见重写正文，保留主线事实并修复重点问题。",
        template=_WRITER_ROOM_REWRITE,
        sort_order=126,
        template_id="63512f59-1ec3-40fe-aac2-7e4a0efa26fa",
    ),
]


async def seed_platform_templates(session):
    """一次性种子数据写入（强制更新：已存在则更新）"""
    import logging
    from sqlmodel import select
    from app.db.models.platform_template import PlatformTemplate
    
    logger = logging.getLogger("ylcraft.seed.platform_templates")
    
    for raw_seed in [*PLATFORM_TEMPLATE_SEEDS, *CREATIVE_PROJECT_TEMPLATE_SEEDS]:
        seed = dict(raw_seed)
        seed.setdefault("template_scope", "image_platform")
        seed.setdefault("template_stage", "platform")
        seed.setdefault("description", None)
        seed.setdefault("system_template", "")
        seed.setdefault("variables", {})
        existing = (await session.execute(
            select(PlatformTemplate).where(PlatformTemplate.platform == seed["platform"])
        )).scalars().first()
        if existing:
            # 只更新业务字段，不要覆盖 id、created_at、updated_at
            existing.name = seed["name"]
            existing.template_scope = seed["template_scope"]
            existing.template_stage = seed["template_stage"]
            existing.description = seed["description"]
            existing.system_template = seed["system_template"]
            existing.outline_template = seed["outline_template"]
            existing.image_template = seed["image_template"]
            existing.page_structure = seed["page_structure"]
            existing.variables = seed["variables"]
            existing.video_template = seed["video_template"]
            existing.default_size = seed["default_size"]
            existing.is_active = seed["is_active"]
            existing.sort_order = seed["sort_order"]
            logger.info(f"Updated platform template: {seed['platform']}")
        else:
            tmpl = PlatformTemplate(**seed)
            session.add(tmpl)
            logger.info(f"Seeded platform template: {seed['platform']}")
    
    await session.commit()
    logger.info(
        "Platform templates seed complete (%s templates)",
        len(PLATFORM_TEMPLATE_SEEDS) + len(CREATIVE_PROJECT_TEMPLATE_SEEDS),
    )
