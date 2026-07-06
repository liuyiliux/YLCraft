"""Built-in Agent Skill templates for YLCraft creative workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import AgentSkill
from app.services.agent.skill_loader import SkillPackageLoader


@dataclass(frozen=True)
class BuiltinSkillTemplate:
    name: str
    description: str
    skill_type: str
    content: str


BUILTIN_SKILL_TEMPLATES: tuple[BuiltinSkillTemplate, ...] = (
    BuiltinSkillTemplate(
        name="creative_project_advance",
        description="检查创作项目缺口，并按大纲、角色、章节、正文、脚本、分镜、参考图的顺序推进。",
        skill_type="workflow",
        content=(
            "推进创作项目时，先读取项目上下文和已有内容，判断最短缺口。"
            "优先补齐会影响后续步骤的结构：项目大纲、角色库、章节规划、单章细纲、正文、脚本、分镜、参考图匹配。"
            "不要跳过版本记录；生成或修改内容后说明写入了什么、还缺什么、下一步建议调用哪个工具。"
        ),
    ),
    BuiltinSkillTemplate(
        name="novel_completion",
        description="补完或重写小说章节正文，让文本更自然、有节奏，并保持前后连续。",
        skill_type="workflow",
        content=(
            "写小说正文前，必须读取项目大纲、章节细纲、角色设定、上一章结尾和本章目标。"
            "正文应按场景推进：动作、对白、心理和环境交替出现，少解释，多让人物通过选择表现性格。"
            "补完时延续原文语气；重写时保留关键事件、角色关系和伏笔，只改善节奏、细节和可读性。"
            "输出前检查：本章目标是否完成、人物动机是否清楚、结尾是否有继续阅读的牵引。"
        ),
    ),
    BuiltinSkillTemplate(
        name="prose_humanize",
        description="降低 AI 腔，增加具体动作、潜台词、停顿和生活细节。",
        skill_type="prompt",
        content=(
            "润色正文时，不要只替换同义词。优先删掉概念化总结，补入可被看见、听见、触摸到的细节。"
            "对白要有遮掩、试探、误会和反应差；人物不要把自己的动机直接讲完。"
            "保留原事件顺序，控制解释密度，让段落长短有变化。"
        ),
    ),
    BuiltinSkillTemplate(
        name="prose_review",
        description="审稿章节正文，指出连贯性、人物动机、节奏和可改写位置。",
        skill_type="prompt",
        content=(
            "审稿时按四类给结论：连续性问题、人物动机问题、节奏问题、可直接改写的句段。"
            "每条问题都要说明影响和建议，不要泛泛评价。若文本可用，明确哪些部分应保留。"
        ),
    ),
    BuiltinSkillTemplate(
        name="character_visual_card",
        description="把角色设定补成可复用的视觉卡，服务立绘、漫画分镜和参考图一致性。",
        skill_type="workflow",
        content=(
            "生成角色视觉卡时，先整合角色身份、剧情作用、性格、年龄、阵营、已有外貌、已有参考图和禁忌风格。"
            "输出应包含：脸部识别点、发型、眼睛、肤色、体型比例、服装结构、材质、配饰、标志物、色板、画风、"
            "一致性规则、负面约束、主立绘提示词、参考图提示词。"
            "如果已有参考图，应说明沿用哪些视觉特征，不要凭空重设角色。"
        ),
    ),
    BuiltinSkillTemplate(
        name="portrait_prompt",
        description="把角色卡转换为单人立绘或九宫格动作参考图提示词。",
        skill_type="prompt",
        content=(
            "立绘提示词要先保证单人、清晰五官、统一服装、干净背景和角色身份一致。"
            "九宫格动作图不要堆太多剧情道具；优先明确 same character、same face、same hairstyle、same outfit。"
            "如目标模型容易出 3D 或真人风，应把画风和负面约束写清楚。"
        ),
    ),
    BuiltinSkillTemplate(
        name="storyboard_generation",
        description="把章节正文或脚本拆成镜头分镜，包含画面、台词、情绪、场景作用和生图提示词。",
        skill_type="workflow",
        content=(
            "生成分镜时，先确认章节目标、场景地点、出场角色、冲突推进和关键台词。"
            "每个镜头至少包含：镜头编号、场景摘要、画面描述、人物动作、情绪、对白/旁白、地点、镜头景别、"
            "场景作用、涉及角色 ID、涉及背景/道具参考 ID、可直接生图的提示词和负面约束。"
            "漫画阅读用图应跟随分镜；脚本图可作为镜头预览，不要和最终漫画页混淆。"
        ),
    ),
    BuiltinSkillTemplate(
        name="reference_match",
        description="根据脚本、分镜或角色卡，匹配素材库里的角色、背景、道具和风格参考图。",
        skill_type="workflow",
        content=(
            "匹配参考图时，先列出本镜头需要稳定的元素：角色脸、服装、背景、道具、画风。"
            "优先使用已绑定到项目、角色或同章节的素材；其次用标签、来源、风格和文本相似度检索。"
            "输出每个参考图的 asset_id、用途、使用权重和备注；找不到时明确建议新生成哪类参考图。"
        ),
    ),
    BuiltinSkillTemplate(
        name="comic_image_prompt",
        description="把分镜和参考图组合成可发给图像模型的漫画生图提示词。",
        skill_type="prompt",
        content=(
            "漫画生图提示词必须由剧情画面、角色一致性、参考图用途、构图、镜头、光线、画风和负面约束组成。"
            "如果有角色或背景参考图，要明确它们的用途：锁脸、服装、场景结构、色调或画风。"
            "不要只写一句剧情摘要；必须让模型知道谁在画面中、在哪里、做什么、情绪是什么、镜头如何观看。"
        ),
    ),
    BuiltinSkillTemplate(
        name="asset_search",
        description="检索素材库，优先找到可直接复用的图片、视频、音频和项目资产。",
        skill_type="workflow",
        content=(
            "搜索素材时，先从项目绑定资产和当前对象关联资产开始，再按类型、标签、来源、状态和关键词扩大范围。"
            "返回结果时说明每个素材为什么匹配，以及还能缺哪类素材。"
        ),
    ),
    BuiltinSkillTemplate(
        name="asset_tagging",
        description="为素材补充类型、风格、来源、状态、角色/项目关联和可检索标签。",
        skill_type="workflow",
        content=(
            "给素材打标签时，区分内容标签、用途标签、风格标签、来源标签和状态标签。"
            "角色立绘、背景、道具、分镜图、漫画图要尽量关联到项目、章节、角色或镜头。"
        ),
    ),
    BuiltinSkillTemplate(
        name="continuity_review",
        description="检查创作项目的连续性，包括人物、设定、章节事件和视觉一致性。",
        skill_type="workflow",
        content=(
            "连续性检查应覆盖：人物动机是否前后一致、事件因果是否断裂、伏笔是否丢失、视觉参考是否冲突。"
            "输出时按严重程度排序，并给出可执行修复建议。"
        ),
    ),
    BuiltinSkillTemplate(
        name="gap_analysis",
        description="识别项目当前缺口，并按影响后续生产的优先级排序。",
        skill_type="workflow",
        content=(
            "缺口分析先判断当前目标，再检查依赖链：大纲、角色、章节、正文、脚本、分镜、参考图、图片产物。"
            "不要只列清单，要说明每个缺口阻塞了哪个后续动作。"
        ),
    ),
    BuiltinSkillTemplate(
        name="platform_source_search",
        description="搜索 B站、小红书、抖音、快手、微博、知乎、公众号等外部平台，并把结果用于素材或项目推进。",
        skill_type="workflow",
        content=(
            "平台搜索前先确认平台、关键词、搜索类型和最大结果数；如果用户只补充平台或关键词，要继承当前对话上下文。"
            "搜索后应总结命中数量、可用结果、可能的账号/登录限制，并建议是否入库素材或继续详情抓取。"
        ),
    ),
    BuiltinSkillTemplate(
        name="download_workflow",
        description="解析链接、磁力、网盘或平台地址，创建下载任务，并把下载结果纳入素材库。",
        skill_type="workflow",
        content=(
            "下载前先判断链接类型、资源来源、是否需要外部访问或账号能力。"
            "涉及写入或消耗型操作时需要确认；下载完成后要记录任务、路径、素材入库状态和失败原因。"
        ),
    ),
    BuiltinSkillTemplate(
        name="image_generation_workflow",
        description="根据项目、角色、分镜和参考图生成图片请求，保存结果、任务和素材血缘。",
        skill_type="workflow",
        content=(
            "生图前必须读取项目/角色/参考图上下文，明确主体、画风、尺寸、负面约束和参考图用途。"
            "不要只跳转页面；应在当前工作流中生成、展示、入库并记录 lineage。"
        ),
    ),
    BuiltinSkillTemplate(
        name="video_generation_workflow",
        description="根据脚本、分镜、参考图或图片资产生成视频任务，并跟踪任务状态。",
        skill_type="workflow",
        content=(
            "视频生成前先确认输入资产、时长、画面运动、镜头目标和模型后端。"
            "生成任务要记录成本提示、任务 ID、轮询方式、产物路径和素材血缘。"
        ),
    ),
    BuiltinSkillTemplate(
        name="subtitle_workflow",
        description="提取、编辑、样式化或烧录字幕，服务短剧、解说、剪辑和发布流程。",
        skill_type="workflow",
        content=(
            "字幕处理前先确认视频来源、语言、输出格式、是否烧录以及字幕样式。"
            "提取和烧录属于任务型操作，要返回任务状态、输出文件和可继续操作。"
        ),
    ),
    BuiltinSkillTemplate(
        name="bgm_workflow",
        description="检索、上传、选择或混入 BGM，服务剪辑、短剧和发布成片。",
        skill_type="workflow",
        content=(
            "BGM 选择要结合场景情绪、节奏、时长和授权状态。"
            "混音或添加到视频前先确认输入视频、音轨、音量和输出路径。"
        ),
    ),
    BuiltinSkillTemplate(
        name="clip_workflow",
        description="调用剪辑引擎执行智能剪辑、解说视频处理、字幕/音频/片段组合。",
        skill_type="workflow",
        content=(
            "剪辑前先确认源视频、脚本/字幕、目标时长、剪辑引擎和输出格式。"
            "任务启动后要跟踪状态，并把输出文件和素材库/项目关联起来。"
        ),
    ),
    BuiltinSkillTemplate(
        name="tts_workflow",
        description="把文本转换为语音，选择音色、语速、格式，并保存音频素材。",
        skill_type="workflow",
        content=(
            "TTS 前先确认文本、语言、音色、语速、输出格式和用途。"
            "生成后应返回音频路径、时长、任务状态，并建议是否加入剪辑或素材库。"
        ),
    ),
    BuiltinSkillTemplate(
        name="ebook_workflow",
        description="从本地文档或文件夹创建电子书，检查章节、封面、元数据和导出状态。",
        skill_type="workflow",
        content=(
            "电子书流程要确认来源目录、章节规则、封面、标题作者和目标格式。"
            "创建任务后跟踪任务状态，输出可下载文件和质检问题。"
        ),
    ),
    BuiltinSkillTemplate(
        name="export_quality_workflow",
        description="导出素材集、项目内容或发布包前做质量检查、去重、合并和格式校验。",
        skill_type="workflow",
        content=(
            "导出前先明确目标平台、格式、素材范围、命名规则和质检标准。"
            "对重复素材、缺失文件、断链血缘和格式错误要先报告，再执行写入型导出。"
        ),
    ),
)


def builtin_skill_names() -> list[str]:
    file_names = [item.name for item in SkillPackageLoader().load_packages()]
    fallback_names = [item.name for item in BUILTIN_SKILL_TEMPLATES]
    return list(dict.fromkeys(file_names + fallback_names))


async def ensure_builtin_skills(session: AsyncSession, user_id: str = "default") -> list[AgentSkill]:
    """Create or refresh built-in skill rows without resetting usage counters."""
    packages = SkillPackageLoader().load_packages()
    package_by_name = {item.name: item for item in packages}
    file_templates = [
        BuiltinSkillTemplate(
            name=item.name,
            description=item.description,
            skill_type=item.skill_type,
            content=item.content,
        )
        for item in packages
    ]
    file_names = {item.name for item in file_templates}
    templates = file_templates + [item for item in BUILTIN_SKILL_TEMPLATES if item.name not in file_names]

    result = await session.execute(
        select(AgentSkill).where(
            AgentSkill.user_id == user_id,
            AgentSkill.name.in_(builtin_skill_names()),
        )
    )
    existing_by_name = {item.name: item for item in result.scalars().all()}
    changed = False

    for template in templates:
        existing = existing_by_name.get(template.name)
        is_builtin = package_by_name.get(template.name).source_type != "user" if template.name in package_by_name else True
        if existing:
            if (
                existing.description != template.description
                or existing.skill_type != template.skill_type
                or existing.content != template.content
                or existing.is_builtin != is_builtin
            ):
                existing.description = template.description
                existing.skill_type = template.skill_type
                existing.content = template.content
                existing.is_builtin = is_builtin
                existing.updated_at = datetime.utcnow()
                changed = True
            continue

        skill = AgentSkill(
            user_id=user_id,
            name=template.name,
            description=template.description,
            skill_type=template.skill_type,
            content=template.content,
            is_builtin=is_builtin,
        )
        session.add(skill)
        existing_by_name[template.name] = skill
        changed = True

    if changed:
        await session.flush()
        for item in existing_by_name.values():
            if item.id is None:
                await session.refresh(item)

    return [existing_by_name[name] for name in [item.name for item in templates] if name in existing_by_name]
