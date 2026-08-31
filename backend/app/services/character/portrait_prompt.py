from __future__ import annotations

import json
from typing import Any


PROMPT_TEMPLATE_VERSION = "character_portrait_v2"

ZH_LANGUAGE_RULE = "语言要求：最终提示词必须以中文开头，主体必须使用中文输出；如果输入里有英文长句或英文段落，必须翻译并改写为中文，不要照抄；只允许在末尾保留少量必要英文模型关键词、风格标签或固定短语，例如 character reference sheet, clean background。"

PORTRAIT_PRESETS = {
    "main_portrait",
    "headshot_icon",
    "key_visual",
    "multi_view_sheet",
    "character_sheet_16_9",
    "identity_board_16_9",
    "expression_pack",
    "expression_grid_3x3",
    "action_pose_pack",
    "pose_grid_3x3",
    "transparent_or_white_background",
    "expression_pose_sheet",
    "item_sheet",
}

PRESET_ALIASES = {
    "": "main_portrait",
    None: "main_portrait",
    "default": "main_portrait",
    "main": "main_portrait",
    "portrait": "headshot_icon",
    "hero": "key_visual",
    "identity_board": "identity_board_16_9",
    "character_sheet": "character_sheet_16_9",
    "expression_grid": "expression_grid_3x3",
    "pose_grid": "pose_grid_3x3",
}

DEFAULT_NEGATIVE_CONSTRAINTS = [
    "多人",
    "脸部崩坏",
    "五官漂移",
    "服装不一致",
    "发型变化",
    "肢体畸形",
    "手指错误",
    "遮挡脸部",
    "裁切头部",
    "裁切脚部",
    "低清晰度",
    "文字",
    "水印",
    "logo",
    "复杂背景",
]

PRESET_NEGATIVE_CONSTRAINTS = {
    "main_portrait": [
        "多视角拼贴",
        "九宫格",
        "重复人物",
    ],
    "headshot_icon": [
        "全身图",
        "错误裁切",
        "五官变形",
        "新增配饰",
        "复杂背景",
    ],
    "key_visual": [
        "身份特征丢失",
        "官方设定服装变化",
        "标志物缺失",
        "严重型崩",
    ],
    "multi_view_sheet": [
        "视图重叠",
        "姿态合并",
        "正侧背不一致",
        "比例漂移",
        "隐藏四肢",
    ],
    "item_sheet": [
        "出现人物",
        "道具重叠",
        "道具缺失",
        "材质错乱",
        "尺寸比例漂移",
        "场景背景",
    ],
    "identity_board_16_9": [
        "文字乱码",
        "密集说明文字",
        "蓝图网格",
        "商品目录排版",
        "角色重叠",
        "姿态合并",
        "跨区遮挡",
    ],
    "character_sheet_16_9": [
        "文字乱码",
        "密集说明文字",
        "角色重叠",
        "姿态合并",
        "跨区遮挡",
        "三视图比例不一致",
    ],
    "expression_pack": [
        "全身图",
        "半身姿态变化过大",
        "脸型变化",
        "发型变化",
        "瞳色变化",
        "配饰变化",
        "表情之间身份漂移",
        "文字标签",
    ],
    "expression_grid_3x3": [
        "非九宫格",
        "格子大小不一",
        "人物跨格",
        "表情重复",
        "脸型变化",
        "发型变化",
        "瞳色变化",
        "配饰变化",
        "文字标签",
    ],
    "action_pose_pack": [
        "服装变化",
        "身体比例变化",
        "姿态重叠",
        "动作融合",
        "肢体缺失",
        "标志物丢失",
        "文字标签",
    ],
    "pose_grid_3x3": [
        "非九宫格",
        "格子大小不一",
        "人物跨格",
        "动作重复",
        "服装变化",
        "身体比例变化",
        "姿态重叠",
        "动作融合",
        "肢体缺失",
        "文字标签",
    ],
    "transparent_or_white_background": [
        "背景物体",
        "复杂光效",
        "脏边",
        "强投影",
        "场景环境",
        "无关道具",
    ],
    "expression_pose_sheet": [
        "脸部漂移",
        "衣服漂移",
        "新增配饰",
        "姿态重叠",
        "表情重复",
        "文字标签",
    ],
}


def normalize_preset(preset: str | None) -> str:
    normalized = PRESET_ALIASES.get(preset, preset or "main_portrait")
    if normalized not in PORTRAIT_PRESETS:
        raise ValueError(f"unsupported portrait preset: {preset}")
    if normalized == "expression_pose_sheet":
        return "expression_pose_sheet"
    return normalized


def synthesize_visual_profile(character: Any, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    identity = _json_obj(getattr(character, "identity_json", {}))
    motivation = _json_obj(getattr(character, "motivation_json", {}))
    speech = _json_obj(getattr(character, "speech_json", {}))
    behavior = _json_obj(getattr(character, "behavior_json", {}))
    ability = _json_obj(getattr(character, "ability_json", {}))
    visual = _json_obj(identity.get("visual_profile"))
    data = {
        "identity_brief": _join_text(
            getattr(character, "name", ""),
            getattr(character, "role", ""),
            getattr(character, "age_range", ""),
            identity.get("alias"),
            identity.get("organization"),
            identity.get("position"),
            identity.get("logline"),
            getattr(character, "personality", ""),
        ),
        "visual_tags": _json_list(visual.get("visual_tags")) or _json_list(getattr(character, "tags", [])),
        "face": visual.get("face") or getattr(character, "appearance", "") or "",
        "hair": visual.get("hair") or identity.get("hair") or "",
        "eyes": visual.get("eyes") or identity.get("eyes") or "",
        "skin": visual.get("skin") or identity.get("skin") or "",
        "temperament": visual.get("temperament") or getattr(character, "personality", "") or "",
        "body_shape": visual.get("body_shape") or identity.get("body_shape") or identity.get("body_profile") or "",
        "body_proportion": visual.get("body_proportion") or identity.get("body_proportion") or "",
        "costume": visual.get("costume") or getattr(character, "costume_hint", "") or "",
        "costume_colors": _json_list(visual.get("costume_colors")),
        "materials": _json_list(visual.get("materials")),
        "shoes": visual.get("shoes") or "",
        "accessories": _json_list(visual.get("accessories")),
        "signature_items": _json_list(visual.get("signature_items")) or _json_list(getattr(character, "signature_items", [])),
        "expression_set": _json_list(visual.get("expression_set")) or _json_list(getattr(character, "expressions", [])) or ["中性", "微笑", "愤怒", "悲伤", "震惊"],
        "pose_set": _json_list(visual.get("pose_set")) or _json_list(getattr(character, "poses", [])) or ["正面站姿", "侧面", "背面", "坐姿", "动作姿态"],
        "style": visual.get("style") or "",
        "background_rule": visual.get("background_rule") or "plain_white_or_soft_off_white",
        "negative_constraints": _json_list(visual.get("negative_constraints")) or DEFAULT_NEGATIVE_CONSTRAINTS.copy(),
        "visual_consistency": _join_text(
            visual.get("visual_consistency"),
            getattr(character, "visual_consistency", ""),
            behavior.get("never_do"),
            behavior.get("boundary"),
            motivation.get("desire"),
            motivation.get("fear"),
            speech.get("tone"),
            ability.get("skills"),
        ),
    }
    return normalize_visual_profile({**data, **(overrides or {})})


def normalize_visual_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = dict(profile or {})
    list_fields = {
        "visual_tags",
        "costume_colors",
        "materials",
        "accessories",
        "signature_items",
        "expression_set",
        "pose_set",
        "negative_constraints",
    }
    text_fields = {
        "identity_brief",
        "face",
        "hair",
        "eyes",
        "skin",
        "temperament",
        "body_shape",
        "body_proportion",
        "costume",
        "shoes",
        "style",
        "background_rule",
        "visual_consistency",
    }
    for field in list_fields:
        profile[field] = _dedupe_strings(profile.get(field))
    for field in text_fields:
        profile[field] = str(profile.get(field) or "").strip()
    if not profile["expression_set"]:
        profile["expression_set"] = ["中性", "微笑", "愤怒", "悲伤", "震惊"]
    if not profile["pose_set"]:
        profile["pose_set"] = ["正面站姿", "侧面", "背面", "坐姿", "动作姿态"]
    profile["negative_constraints"] = _dedupe_strings(
        [*DEFAULT_NEGATIVE_CONSTRAINTS, *profile.get("negative_constraints", [])]
    )
    if not profile["background_rule"]:
        profile["background_rule"] = "plain_white_or_soft_off_white"
    return profile


def build_portrait_prompt(
    *,
    character: Any,
    preset: str | None = "main_portrait",
    prompt_override: str | None = None,
    visual_profile: dict[str, Any] | None = None,
    style_override: str = "",
    negative_override: str = "",
    language: str = "zh",
) -> dict[str, Any]:
    selected_preset = normalize_preset(preset)
    snapshot = synthesize_visual_profile(character, visual_profile)
    style = (style_override or snapshot.get("style") or "高质量角色设定图，干净线条，专业角色设计").strip()

    if prompt_override and prompt_override.strip():
        prompt = prompt_override.strip()
    else:
        prompt = _preset_prompt(selected_preset, character, snapshot, style)
    negative_prompt = "，".join(
        _dedupe_strings(
            [
                *snapshot["negative_constraints"],
                *PRESET_NEGATIVE_CONSTRAINTS.get(selected_preset, []),
                negative_override,
            ]
        )
    )
    return {
        "preset": selected_preset,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "visual_profile_snapshot": snapshot,
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "language": language or "zh",
    }


def _preset_prompt(preset: str, character: Any, profile: dict[str, Any], style: str) -> str:
    name = getattr(character, "name", "") or "未命名角色"
    common = [
        f"单人角色：{name}",
        _line("身份简述", profile["identity_brief"]),
        _line("外貌/脸部识别点", profile["face"]),
        _line("发型", profile["hair"]),
        _line("眼睛", profile["eyes"]),
        _line("肤色/皮肤特征", profile["skin"]),
        _line("气质", profile["temperament"]),
        _line("体型", profile["body_shape"]),
        _line("身体比例", profile["body_proportion"]),
        _line("服装", profile["costume"]),
        _line("服装配色", "、".join(profile["costume_colors"])),
        _line("材质", "、".join(profile["materials"])),
        _line("鞋履", profile["shoes"]),
        _line("配饰", "、".join(profile["accessories"])),
        _line("标志物", "、".join(profile["signature_items"])),
        _line("一致性规则", profile["visual_consistency"]),
        _line("画风", style),
        ZH_LANGUAGE_RULE,
        "必须保持同一个角色身份、同一张脸、同一发型、同一服装结构、同一身体比例。",
    ]

    if preset == "multi_view_sheet":
        intent = [
            "输出标准 Turnaround 三视图角色模型表，作为生产执行基准。",
            "包含正面、侧面、背面三个全身视图，姿态中性，清楚展示服装结构和配饰位置。",
            "统一头身比、肩宽、躯干四肢长度、五官位置、线条粗细和固有色。",
            "纯白背景，无氛围光影、无场景、无动态倾斜；每个视图之间留出明确空隙，不重叠，不遮挡，不裁切头脚。",
        ]
    elif preset == "identity_board_16_9":
        intent = [
            "输出 16:9 角色总览身份板 Summary Board，定位是企划/编剧/导演快速查阅，不作为作画生产基准。",
            "画面中心或右侧放一张高质量主立绘，展示角色气质、核心服装和代表道具。",
            "左侧或上方预留精简信息区：姓名、身份、阵营、一句话人设、标志性外貌特征、代表道具、版本状态。",
            "允许放三视图、典型表情、关键道具的极小缩略预览，但只能作为摘要预览，不要完整精细生产图纸。",
            f"典型表情缩略预览最多 3 个：{'、'.join(profile['expression_set'][:3])}。",
            "局部细节最多 3-5 个，例如发丝、衣领、吊坠、疤痕、武器或标志配饰。",
            "版面干净、有层级、有留白；不要把完整三视图、九宫格表情、大段背景文案塞进身份板。",
        ]
    elif preset == "character_sheet_16_9":
        intent = [
            "输出 16:9 角色设定板 Character Sheet，左侧约 34% 放半身主立绘，右侧放正面/侧面/背面三视图与少量细节条。",
            "角色设定板用于企划、编剧、导演和后续生图快速查阅；所有视图必须保持同一张脸、发型、服装结构和身体比例。",
            "右侧三视图采用中性站姿，视图之间留出清晰间隔，不重叠、不遮挡、不裁切头脚。",
            "底部或侧边只放少量视觉细节缩略图，例如发丝、衣领、吊坠、疤痕、武器或标志配饰。",
            "不要生成大段说明文字；如需文字标签，由系统后续在页面或导出时叠加。",
            f"典型表情缩略预览最多 3 个：{'、'.join(profile['expression_set'][:3])}。",
            "局部细节最多 3-5 个，例如发丝、衣领、吊坠、疤痕、武器或标志配饰。",
            "纯白或浅灰背景，分区光照，版面干净有层级；不要塞入九宫格表情或大段背景文案。",
        ]
    elif preset == "expression_pack":
        intent = [
            "输出单角色表情包设定板。",
            f"包含多个正面头像表情：{'、'.join(profile['expression_set'])}。",
            "所有头像保持同一脸型、发型、眼睛、肤色、配饰和服装领口，不改变身份。",
            "不要在图片里生成文字标签；如需标签，由系统后续在页面或导出时叠加。",
        ]
    elif preset == "expression_grid_3x3":
        expressions = _grid_items(profile["expression_set"], ["中性", "微笑", "愤怒", "悲伤", "震惊", "害羞", "疑惑", "冷笑", "哭泣"])
        intent = [
            "注意：表情九宫格用于后续切成素材，不建议作为第一张锁脸图；如果有主立绘、身份板或多视图参考图，必须以参考图为最高优先级。",
            "输出单角色表情九宫格，严格 3x3 grid，九个等宽等高格子，白色留白分隔线，整齐边距。",
            f"每格一个正面头像表情，按顺序包含：{'、'.join(expressions)}。",
            "所有九个格子必须是同一角色，不重新设计人物，不改变年龄、气质、脸型或任何标志性特征。",
            "严格保持一致：五官比例、脸型轮廓、眼睛大小、眼型、虹膜颜色、眉毛形状、鼻梁高度、嘴唇厚度、下巴轮廓、发际线、发型、发量、肤色、配饰和服装领口。",
            "不要在格子内生成文字标签；图片只保留表情头像，标签由系统后续叠加。",
            "构图应便于后续按固定 3x3 网格切割为 9 张表情素材。",
            "脸部质量优先：清晰眼睛、稳定瞳色、细致睫毛、对称五官、不要让任何一格五官糊掉或消失。",
        ]
    elif preset == "action_pose_pack":
        intent = [
            "输出单角色动作姿态设定板。",
            f"包含多个姿态：{'、'.join(profile['pose_set'])}。",
            "所有姿态保持同一服装、同一身体比例、同一标志物，姿态之间清楚分隔。",
            "不要在图片里生成文字标签；如需标签，由系统后续在页面或导出时叠加。",
        ]
    elif preset == "pose_grid_3x3":
        poses = _grid_items(
            profile["pose_set"],
            ["自然站立", "双手插兜", "双臂交叉", "单手整理领带", "单手插兜另一手自然下垂", "单手向前示意", "双手背在身后", "微微侧身站立", "回头站姿"],
        )
        intent = [
            "注意：动作九宫格用于在角色身份已经稳定后生成动作素材，不建议作为第一张锁脸图；如果有主立绘、身份板或多视图参考图，必须以参考图为最高优先级。",
            "输出单角色动作姿态九宫格，严格 3x3 grid，九个等宽等高格子，白色留白分隔线，整齐边距。",
            f"每格一个完整身体动作姿态，按顺序包含：{'、'.join(poses)}。",
            "九个动作都以站姿或轻微身体变化为主，不要坐下、蹲下、奔跑、跳跃、打斗或加入复杂道具，避免模型把细节预算分配给道具和大动作。",
            "所有九个格子必须是同一角色，不重新设计人物，不改变年龄、气质、脸型或任何标志性特征。",
            "严格保持一致：同一张脸、同一发型、同一眼型和瞳色、同一身体比例、同一肩宽、同一手部比例、同一服装结构、同一材质、同一配饰、同一标志物。",
            "人物不能跨格，姿态之间不能重叠，四肢完整，不裁切头部和脚部。",
            "不要在格子内生成文字标签；图片只保留动作姿态，标签由系统后续叠加。",
            "构图应便于后续按固定 3x3 网格切割为 9 张动作素材。",
            "每格人物大小一致，头部和脚部完整，边距统一，浅灰或纯净背景，光线均匀。",
            "脸部质量优先：即使是全身小人，也要保留清晰眼睛、稳定五官和可辨识脸部身份。",
        ]
    elif preset == "transparent_or_white_background":
        intent = [
            "输出单人全身或膝上立绘素材。",
            "背景使用透明底、纯白或柔和灰白；不出现环境、无关道具、logo、水印。",
            "轮廓干净，适合后续抠图、Live2D、分镜和漫画合成复用。",
        ]
    elif preset == "headshot_icon":
        intent = [
            "输出角色头像/半身图标素材。",
            "胸像或头像裁切，聚焦五官、眼睛、发型、气质和服装领口，背景干净。",
            "适合 UI 头像、对话框头像、角色列表封面；不要改变核心五官、发色、瞳色、配饰。",
        ]
    elif preset == "key_visual":
        intent = [
            "输出氛围感宣传立绘 Key Visual。",
            "允许艺术光影、戏剧构图、场景氛围和情绪化动态，但角色身份特征必须严格对齐设定。",
            "突出完整穿搭、代表道具和角色辨识度，适合封面、海报、PV、片头使用。",
            "不能作为修改三视图比例和官方服饰结构的依据。",
        ]
    elif preset == "expression_pose_sheet":
        intent = [
            "输出紧凑的角色表情与姿态设定板。",
            f"表情包含：{'、'.join(profile['expression_set'])}。",
            f"姿态包含：{'、'.join(profile['pose_set'])}。",
            "同一套服装与身体比例贯穿所有样本，避免脸部漂移、衣服漂移和新增配饰。",
        ]
    elif preset == "item_sheet":
        item_focus = "、".join(profile["signature_items"]) or "角色代表道具"
        accessory_focus = "、".join(profile["accessories"])
        intent = [
            "输出角色道具与标志物设定板 Item Sheet，作为美术建模和作画参考。",
            f"核心道具必须包含：{item_focus}。",
            f"配饰参考：{accessory_focus}。" if accessory_focus else "",
            "每件道具单独成图、互不重叠，给出正面与 3/4 侧面两个角度，清楚展示结构、材质、固有色、尺寸比例和做旧磨损状态。",
            "纯白背景，画面中不出现人物、场景、文字和水印；道具之间留出明确空隙，不裁切边缘。",
            "道具的材质质感、配色和装饰语言必须与角色服装保持一致。",
        ]
    else:
        intent = [
            "输出主立绘。",
            "单人、清晰脸部、全身或膝上构图，姿态自然，服装和标志物清楚可辨。",
            "简洁纯色或柔和灰白背景，适合作为角色库封面和后续一致性参考图。",
        ]

    return "\n".join([line for line in [*intent, *common, "高质量，细节明确，统一光照，character reference sheet, clean background."] if line])


def _line(label: str, value: str) -> str:
    value = (value or "").strip()
    return f"{label}：{value}" if value else ""


def _join_text(*values: Any) -> str:
    return "，".join(str(value).strip() for value in values if str(value or "").strip())


def _grid_items(values: list[str], fallback: list[str]) -> list[str]:
    return _dedupe_strings([*(values or []), *fallback])[:9]


def _json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            parsed = [value]
        return _dedupe_strings(parsed)
    return _dedupe_strings(value)


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _dedupe_strings(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    result: list[str] = []
    seen = set()
    for value in values if isinstance(values, list) else list(values):
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
