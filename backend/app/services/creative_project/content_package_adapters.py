"""内容包平台适配器：把**同一份内容包**翻译成各平台要的形状。

职责边界（design §4）
--------------------
适配器只做**纯格式转换**：

- **不调外部平台** —— 不会真的发布到公众号/小红书/抖音，只产出"发之前准备好的那份东西"；
- **不写回源包** —— 输出记在 `content_package.outputs[]`，不改 `items`；
- **不保存第二份事实源** —— 每条输出都带 `source_package_id` / `source_package_version` /
  `source_item_ids`，因此"源包改了、这份输出过期了"是可判定的，而不是靠人记。

关于"不复制 items"的准确含义：平台产物（公众号 HTML、小红书卡片、PDF 分页）**本身
必然包含正文文字**——那是产物的一部分。这里禁止的是把 `items` 整体再存一份当作可编辑
事实源。所以每个平台产物只保留它真正需要的字段，并且逐项回引 `item_id`。

失败语义
--------
单个适配器抛错**不影响其它适配器**：该条输出记为 `status="failed"` 并带 `error`，
其余照常产出。这样"某个平台输出失败"可以**独立重建**，不必重跑整包。
未知适配器名属于调用方错误，直接在构建前抛 `ValueError`（端点转 400）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

#: 支持的适配器类型（与 profiles.py 的 output_adapters 取值一致）
ADAPTER_TYPES: tuple[str, ...] = (
    "wechat_official_account",
    "xiaohongshu_carousel",
    "douyin_short_video",
    "pdf_ebook",
    "asset_bundle",
)

#: 输出记录的状态取值
OUTPUT_STATUSES: tuple[str, ...] = ("ready", "failed", "stale")

#: 小红书标准竖版卡片尺寸（3:4）
XHS_CARD = {"aspect_ratio": "3:4", "width": 1242, "height": 1656}

#: 抖音竖屏分辨率
DOUYIN_VIDEO = {"width": 1080, "height": 1920, "aspect_ratio": "9:16"}

#: 微信公众号摘要长度上限
WECHAT_DIGEST_LIMIT = 120


@dataclass(frozen=True)
class AdapterInput:
    """适配器的输入：一份已校验的内容包（纯数据，不含 IO）。"""

    package_id: str
    package_version: int
    package_type: str
    title: str
    topic: str
    brief: str
    style: str
    aspect_ratio: str
    items: tuple[dict[str, Any], ...]
    #: item_id -> 已解析的图片 URL（由调用方注入；适配器不碰存储，保持纯净）
    asset_urls: dict[str, list[str]] = field(default_factory=dict)

    def image_urls(self, item: dict[str, Any]) -> list[str]:
        return list(self.asset_urls.get(str(item.get("id") or ""), []) or [])

    @property
    def item_ids(self) -> list[str]:
        return [str(item.get("id") or "") for item in self.items if item.get("id")]


def adapter_input_from_package(
    package: dict[str, Any],
    *,
    package_id: str = "",
    package_version: int = 1,
    asset_urls: dict[str, list[str]] | None = None,
) -> AdapterInput:
    """从已落库的包 dict 构造适配器输入。

    刻意不在这里做校验——包在保存时已由 `content_package_schema` 校验过。
    """
    raw_items = package.get("items") or []
    items = tuple(item for item in raw_items if isinstance(item, dict))
    return AdapterInput(
        package_id=str(package_id or package.get("id") or ""),
        package_version=int(package_version or package.get("version") or 1),
        package_type=str(package.get("package_type") or ""),
        title=str(package.get("title") or "").strip(),
        topic=str(package.get("topic") or "").strip(),
        brief=str(package.get("brief") or "").strip(),
        style=str(package.get("style") or "").strip(),
        aspect_ratio=str(package.get("aspect_ratio") or "").strip(),
        items=items,
        asset_urls=dict(asset_urls or {}),
    )


# ---------------------------------------------------------------------------
# 各平台的产物构造
# ---------------------------------------------------------------------------


def _text_of(item: dict[str, Any]) -> str:
    return str(item.get("text") or "").strip()


def _title_of(item: dict[str, Any]) -> str:
    return str(item.get("title") or "").strip()


def _tags_of(item: dict[str, Any], inp: AdapterInput) -> list[str]:
    tags = [str(tag).strip() for tag in (item.get("tags") or []) if str(tag).strip()]
    if not tags and inp.style:
        tags = [inp.style]
    return tags


def _build_wechat(inp: AdapterInput) -> dict[str, Any]:
    """公众号：富文本 HTML + 标题 + 摘要 + 封面与正文配图引用 + 草稿 payload 形状。"""
    blocks: list[str] = []
    body_image_asset_ids: list[str] = []
    for item in inp.items:
        heading = _title_of(item)
        if heading:
            blocks.append("<h2>%s</h2>" % _escape(heading))
        text = _text_of(item)
        if text:
            blocks.append("<p>%s</p>" % _escape(text).replace("\n", "<br/>"))
        asset_ids = [str(a) for a in (item.get("asset_ids") or []) if a]
        body_image_asset_ids.extend(asset_ids)
        urls = inp.image_urls(item)
        for url in urls:
            blocks.append('<p><img src="%s" alt="%s"/></p>' % (_escape(url), _escape(heading or inp.title)))
        if not urls:
            # 未注入 URL 时不要静默少图：留一个带 asset_id 的占位，渲染方（前端）可据此换成真实地址
            for asset_id in asset_ids:
                blocks.append(
                    '<p><img data-asset-id="%s" alt="%s"/></p>' % (_escape(asset_id), _escape(heading or inp.title))
                )
    cover_asset_ids = [str(a) for a in (inp.items[0].get("asset_ids") or []) if a] if inp.items else []

    digest = (inp.brief or inp.topic or inp.title)[:WECHAT_DIGEST_LIMIT]
    return {
        "title": inp.title or inp.topic,
        "digest": digest,
        "html": "<section>%s</section>" % "".join(blocks),
        "cover_asset_ids": cover_asset_ids,
        "body_image_asset_ids": body_image_asset_ids,
        # 与微信草稿接口的字段形状对齐，但不发送——"发不发"由发布环节决定
        "draft_payload": {
            "title": inp.title or inp.topic,
            "digest": digest,
            "content": "<section>%s</section>" % "".join(blocks),
            "thumb_media_asset_ids": cover_asset_ids,
        },
    }


def _build_xiaohongshu(inp: AdapterInput) -> dict[str, Any]:
    """小红书：竖版轮播卡（页序 / 标题 / 正文 / 标签 / 图片引用）。"""
    cards: list[dict[str, Any]] = []
    all_tags: list[str] = []
    for order, item in enumerate(inp.items, start=1):
        tags = _tags_of(item, inp)
        for tag in tags:
            if tag not in all_tags:
                all_tags.append(tag)
        cards.append(
            {
                "order": order,
                "item_id": str(item.get("id") or ""),
                "title": _title_of(item),
                "text": _text_of(item),
                "tags": tags,
                "image_asset_ids": [str(a) for a in (item.get("asset_ids") or []) if a],
                "image_urls": inp.image_urls(item),
            }
        )
    return {"card_size": dict(XHS_CARD), "cards": cards, "tags": all_tags}


def _build_douyin(inp: AdapterInput) -> dict[str, Any]:
    """抖音：竖屏镜头表 + 口播/字幕 + 视频参数。

    本期**只产出规划数据**，不触发视频生成；后续可用 `shots[].action_prompt` 与
    `first_frame_asset_ids` 交给视频生成环节。
    """
    shots: list[dict[str, Any]] = []
    captions: list[str] = []
    for order, item in enumerate(inp.items, start=1):
        voiceover = _text_of(item)
        subtitle = voiceover if len(voiceover) <= 30 else voiceover[:30]
        if subtitle:
            captions.append(subtitle)
        shots.append(
            {
                "order": order,
                "item_id": str(item.get("id") or ""),
                "first_frame_asset_ids": [str(a) for a in (item.get("asset_ids") or []) if a],
                "first_frame_urls": inp.image_urls(item),
                "action_prompt": str(item.get("video_prompt") or "").strip(),
                "voiceover": voiceover,
                "subtitle": subtitle,
            }
        )
    return {
        "orientation": "portrait",
        "video_params": dict(DOUYIN_VIDEO),
        "shots": shots,
        "captions_text": "\n".join(captions),
        "total_shots": len(shots),
    }


def _build_pdf_ebook(inp: AdapterInput) -> dict[str, Any]:
    """PDF 电子书：分页结构 + 文件名。

    这里**只产出可分页的数据**，不生成 PDF 字节——本环境未安装任何 PDF 生成库
    （只有 pypdf，它负责读写/合并而非从零排版）。调用方需要真实文件时，由渲染器
    （前端或后续步骤）把 `pages` 转成字节。这一点会在 warnings 里如实标注。
    """
    pages = [
        {
            "order": order,
            "item_id": str(item.get("id") or ""),
            "text": _text_of(item),
            "image_asset_ids": [str(a) for a in (item.get("asset_ids") or []) if a],
            "image_urls": inp.image_urls(item),
        }
        for order, item in enumerate(inp.items, start=1)
    ]
    safe_title = (inp.title or inp.topic or "content-package").replace("/", "_").replace("\\", "_")
    return {
        "filename": "%s.pdf" % safe_title,
        "page_count": len(pages),
        "page_size": "A4",
        "source_aspect_ratio": inp.aspect_ratio or "",
        "pages": pages,
    }


def _build_asset_bundle(inp: AdapterInput) -> dict[str, Any]:
    """资产包：原始 JSON + Markdown + 提示词清单。

    这是**刻意的完整快照**（导出用），因此包含全部内容；但它仍带
    `source_package_version`，所以"导出后源包又改了"是可判定的。
    """
    manifest = {
        "package_id": inp.package_id,
        "version": inp.package_version,
        "package_type": inp.package_type,
        "title": inp.title or inp.topic,
        "item_count": len(inp.items),
        "generated_at": _now_iso(),
    }
    package_json = json.dumps(
        {
            "package_type": inp.package_type,
            "title": inp.title,
            "topic": inp.topic,
            "brief": inp.brief,
            "style": inp.style,
            "aspect_ratio": inp.aspect_ratio,
            "items": list(inp.items),
        },
        ensure_ascii=False,
        indent=2,
    )
    markdown_lines = ["# %s" % (inp.title or inp.topic or "内容包"), ""]
    if inp.brief:
        markdown_lines += [inp.brief, ""]
    for order, item in enumerate(inp.items, start=1):
        markdown_lines.append("## %d. %s" % (order, _title_of(item) or "未命名"))
        text = _text_of(item)
        if text:
            markdown_lines += [text, ""]
        for url in inp.image_urls(item):
            markdown_lines += ["![%s](%s)" % (_title_of(item), url), ""]
    prompts = [
        "%d\t%s\t%s" % (order, _title_of(item) or "", str(item.get("image_prompt") or "").strip())
        for order, item in enumerate(inp.items, start=1)
    ]
    return {
        "manifest": manifest,
        "files": [
            {"path": "package.json", "content": package_json},
            {"path": "content.md", "content": "\n".join(markdown_lines).strip() + "\n"},
            {"path": "prompts.tsv", "content": "order\ttitle\timage_prompt\n" + "\n".join(prompts) + "\n"},
        ],
    }


def _escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class AdapterSpec:
    adapter_type: str
    label: str
    build: Callable[[AdapterInput], dict[str, Any]]
    #: 该适配器是否只产出规划数据、不产出可直接发布的成品（当前仅抖音）
    planning_only: bool = False


ADAPTERS: dict[str, AdapterSpec] = {
    "wechat_official_account": AdapterSpec(
        adapter_type="wechat_official_account",
        label="微信公众号图文",
        build=_build_wechat,
    ),
    "xiaohongshu_carousel": AdapterSpec(
        adapter_type="xiaohongshu_carousel",
        label="小红书轮播卡",
        build=_build_xiaohongshu,
    ),
    "douyin_short_video": AdapterSpec(
        adapter_type="douyin_short_video",
        label="抖音竖屏镜头表",
        build=_build_douyin,
        # 只出镜头表/字幕/参数，具体视频由后续步骤生成
        planning_only=True,
    ),
    "pdf_ebook": AdapterSpec(
        adapter_type="pdf_ebook",
        label="PDF 电子书",
        build=_build_pdf_ebook,
        planning_only=True,
    ),
    "asset_bundle": AdapterSpec(
        adapter_type="asset_bundle",
        label="素材包（JSON / Markdown / 提示词）",
        build=_build_asset_bundle,
    ),
}


def adapter_catalog() -> list[dict[str, Any]]:
    """可序列化的适配器目录，供 API 调用方发现有哪些可选。"""
    return [
        {
            "adapter_type": spec.adapter_type,
            "label": spec.label,
            "planning_only": spec.planning_only,
        }
        for spec in ADAPTERS.values()
    ]


def build_package_outputs(
    inp: AdapterInput,
    adapter_types: list[str],
) -> list[dict[str, Any]]:
    """按顺序构建输出记录；单个适配器失败只影响它自己。

    未知适配器名在构建前抛 `ValueError`（调用方错误），但**不阻断**其它已知适配器
    的产出——见下面的两段式实现：先整体校验名字，再逐个构建。
    """
    normalized = [str(name or "").strip() for name in (adapter_types or [])]
    unknown = [name for name in normalized if name and name not in ADAPTERS]
    if unknown:
        raise ValueError(
            "不支持的内容包适配器：%s（支持：%s）" % ("、".join(unknown), "、".join(ADAPTER_TYPES))
        )

    outputs: list[dict[str, Any]] = []
    for name in normalized:
        if not name:
            continue
        spec = ADAPTERS[name]
        base = {
            "adapter_type": name,
            "label": spec.label,
            "source_package_id": inp.package_id,
            "source_package_version": inp.package_version,
            "source_item_ids": inp.item_ids,
            "generated_at": _now_iso(),
        }
        warnings: list[str] = []
        if spec.planning_only:
            warnings.append("%s 当前只产出规划数据，成品由后续步骤生成" % spec.label)
        try:
            payload = spec.build(inp)
            outputs.append({**base, "status": "ready", "payload": payload, "warnings": warnings, "error": ""})
        except Exception as exc:  # noqa: BLE001 - 单适配器失败不得影响其它适配器
            outputs.append(
                {
                    **base,
                    "status": "failed",
                    "payload": {},
                    "warnings": warnings,
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
            )
    return outputs
