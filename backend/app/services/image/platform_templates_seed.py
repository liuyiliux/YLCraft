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

async def seed_platform_templates(session):
    """一次性种子数据写入（强制更新：已存在则更新）"""
    import logging
    from sqlmodel import select
    from app.db.models.platform_template import PlatformTemplate
    
    logger = logging.getLogger("ylcraft.seed.platform_templates")
    
    for seed in PLATFORM_TEMPLATE_SEEDS:
        existing = (await session.execute(
            select(PlatformTemplate).where(PlatformTemplate.platform == seed["platform"])
        )).scalars().first()
        if existing:
            # 只更新业务字段，不要覆盖 id、created_at、updated_at
            existing.name = seed["name"]
            existing.outline_template = seed["outline_template"]
            existing.image_template = seed["image_template"]
            existing.page_structure = seed["page_structure"]
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
    logger.info(f"Platform templates seed complete ({len(PLATFORM_TEMPLATE_SEEDS)} platforms)")
