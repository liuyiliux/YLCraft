"""内容包类型 schema（按 `package_type` 声明契约并在保存时校验）。

背景
----
内容包契约（`design.md` §2）把 `items` 定义为**最小可重跑单元**，但在此之前
`save_content_package` 只校验了「包类型与 profile 一致 + items 是对象数组」——
任何类型都接受任意字段，四种较晚才排期的类型（article_package / social_carousel /
shot_list / single_media）因此**没有任何契约**，API 调用方无从知道该给什么。

本模块把这 6 种类型的契约集中声明，并在保存路径上按类型校验。

硬校验 vs 软提示
----------------
校验刻意分成两档，因为**生成是 LLM 驱动的**：把"缺字段"一律当硬错误会让一次
模型抖动直接变成保存失败。

- **硬错误**（`ValueError`）：结构性、无法安全落库的问题——未知包类型、items 不是
  数组、item 不是对象、`status` 不在取值域内、条数超出上限。
- **软提示**（返回 `warnings`）：条数低于推荐下限、个别 item 缺推荐字段、
  **整个包没有任何媒体提示词**。调用方可据此提示用户补齐，但不阻断保存。

  最后一条刻意不做硬错误：内容包是**增量编辑**的产物，"先存标题、再补提示词"是
  正常中间态（本项目的版本追加接口就被这样使用），硬拒会让 API 调用方无法保存
  半成品版本。

`ui_enabled` 是"本期只做 API、不建 UI"的开关标记：`page_book` 与
`knowledge_cards` 已有工作台，其余四种为 False。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: schema 版本。字段语义发生不兼容变化时递增，并随包一起落库，便于事后判断
#: 某个历史包是按哪一版契约校验的。
SCHEMA_VERSION = 1

#: item 状态取值域（design §5.3）
ITEM_STATUSES: tuple[str, ...] = (
    "draft",
    "ready",
    "generating",
    "succeeded",
    "failed",
    "stale",
    "archived",
)

#: 所有类型共用的 item 字段（生成提示词、事实来源、谱系引用等）
COMMON_ITEM_FIELDS: tuple[str, ...] = (
    "id",
    "index",
    "title",
    "text",
    "fact",
    "source",
    "source_url",
    "image_prompt",
    "video_prompt",
    "source_refs",
    "asset_ids",
    "status",
)


@dataclass(frozen=True)
class PackageSchema:
    """一种内容包类型的契约声明。"""

    package_type: str
    label: str
    #: 条数边界。`min_recommended` 只产生 warnings，`max_items` 是硬上限
    #: （防止把明显不合理的超大包写进库）。
    min_recommended: int
    max_items: int
    #: 每个 item 推荐携带的字段；缺失只提示不报错。
    recommended_item_fields: tuple[str, ...] = ()
    #: 包级额外字段（除 items/outputs/source_context 之外的）
    package_fields: tuple[str, ...] = ()
    #: 该类型是否需要媒体生成提示词（决定"无法出图"的硬校验是否生效）
    requires_media_prompt: bool = True
    #: 默认媒体形态，供适配器与前端展示提示
    default_media: str = "image"
    #: 本期是否已有工作台；False = 仅 API 可用（不建 UI）
    ui_enabled: bool = False
    description: str = ""


PACKAGE_SCHEMAS: dict[str, PackageSchema] = {
    "page_book": PackageSchema(
        package_type="page_book",
        label="绘本 / 漫画页",
        min_recommended=1,
        max_items=120,
        recommended_item_fields=("title", "image_prompt"),
        default_media="image",
        ui_enabled=True,
        description="逐页的绘本/漫画：每页有页文字与图片提示词，可批量出图后按页排版。",
    ),
    "knowledge_cards": PackageSchema(
        package_type="knowledge_cards",
        label="科普知识卡",
        min_recommended=1,
        max_items=120,
        # fact/source 只在非 prompt_only 模式下必填，故仅作推荐项
        recommended_item_fields=("title", "fact", "image_prompt"),
        default_media="image",
        ui_enabled=True,
        description="科普图文：总介绍 + 若干知识卡，每卡含可核验事实与来源占位。",
    ),
    "article_package": PackageSchema(
        package_type="article_package",
        label="文章内容单元",
        min_recommended=1,
        max_items=80,
        recommended_item_fields=("text",),
        # 文章整体成篇，这几项属于包级而非逐条
        package_fields=("title_candidates", "lead", "markdown", "html"),
        requires_media_prompt=False,
        default_media="doc",
        ui_enabled=False,
        description="一次规划出整篇文章：标题候选、导语、正文段落、封面与配图提示词，可导出 Markdown/HTML。",
    ),
    "social_carousel": PackageSchema(
        package_type="social_carousel",
        label="图文轮播卡",
        min_recommended=6,
        max_items=10,
        recommended_item_fields=("title", "text", "image_prompt"),
        default_media="image",
        ui_enabled=False,
        description="6-10 张轮播卡：每卡标题、正文与图片提示词，可直接喂给小红书等平台的轮播适配器。",
    ),
    "shot_list": PackageSchema(
        package_type="shot_list",
        label="镜头表",
        min_recommended=1,
        max_items=60,
        recommended_item_fields=("image_prompt", "video_prompt", "text"),
        package_fields=("duration_seconds",),
        default_media="video",
        ui_enabled=False,
        description="按镜头规划：首帧提示词、动作提示词、口播/字幕文本，可出图或出视频。",
    ),
    "single_media": PackageSchema(
        package_type="single_media",
        label="单个媒体创意",
        min_recommended=1,
        max_items=1,
        recommended_item_fields=("image_prompt",),
        default_media="image",
        ui_enabled=False,
        description="一句创意或一张参考素材 → 一个图片/视频规划，用于快速试做。",
    ),
}


def get_package_schema(package_type: str) -> PackageSchema:
    """取某类型的 schema；未知类型抛 `ValueError`（与其它校验错误同一处理路径）。"""
    normalized = str(package_type or "").strip()
    schema = PACKAGE_SCHEMAS.get(normalized)
    if schema is None:
        raise ValueError(
            "不支持的内容包类型：%s（支持：%s）" % (normalized or "(空)", "、".join(sorted(PACKAGE_SCHEMAS)))
        )
    return schema


def schema_descriptor(package_type: str) -> dict[str, Any]:
    """可序列化的 schema 摘要，随保存的包一起落库，便于调用方与历史包对齐契约。"""
    schema = get_package_schema(package_type)
    return {
        "package_type": schema.package_type,
        "version": SCHEMA_VERSION,
        "ui_enabled": schema.ui_enabled,
        "default_media": schema.default_media,
        "min_recommended_items": schema.min_recommended,
        "max_items": schema.max_items,
        "recommended_item_fields": list(schema.recommended_item_fields),
        "package_fields": list(schema.package_fields),
    }


def validate_content_package(
    package_type: str,
    package: dict[str, Any],
    items: list[dict[str, Any]],
) -> list[str]:
    """按类型校验内容包；返回**软提示**列表，硬错误直接抛 `ValueError`。

    调用方约定：`items` 已由保存路径归一化（含 id / index / status 等），因此本函数
    不必再补默认值，只做契约检查。
    """
    schema = get_package_schema(package_type)
    warnings: list[str] = []

    if len(items) > schema.max_items:
        raise ValueError(
            "%s 的条目数上限为 %d，当前 %d 条" % (schema.label, schema.max_items, len(items))
        )

    for position, item in enumerate(items, start=1):
        status = str(item.get("status") or "draft")
        if status not in ITEM_STATUSES:
            raise ValueError(
                "第 %d 项的 status 非法：%s（允许：%s）"
                % (position, status, "、".join(ITEM_STATUSES))
            )

    if schema.requires_media_prompt and items:
        # 整个包都没有生成提示词 → 当前无法出图。提示而非拒绝：内容包是增量编辑的，
        # "先存标题再补提示词"是正常中间态，硬拒会让调用方存不了半成品版本。
        usable = any(
            str(item.get("image_prompt") or "").strip() or str(item.get("video_prompt") or "").strip()
            for item in items
        )
        if not usable:
            warnings.append("%s 目前没有任何 image_prompt / video_prompt，暂不可出图" % schema.label)

    if items and len(items) < schema.min_recommended:
        warnings.append(
            "%s 建议至少 %d 条，当前 %d 条" % (schema.label, schema.min_recommended, len(items))
        )

    if schema.recommended_item_fields:
        missing_counts = {field: 0 for field in schema.recommended_item_fields}
        for item in items:
            for field in schema.recommended_item_fields:
                if not str(item.get(field) or "").strip():
                    missing_counts[field] += 1
        for field, count in missing_counts.items():
            if count:
                warnings.append("%s：%d/%d 条缺少 %s" % (schema.label, count, len(items), field))

    return warnings
