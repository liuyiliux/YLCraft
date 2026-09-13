"""可复用的内容规划器（ContentPackagePlanner）。

背景与动机
----------
「主题 → 结构化规划」这件事此前只存在于 `outline_service.py` 内部，且只产出**按平台
聚合**的大纲形状（`{platform: {title, copywriting, pages}}`）。内容包工作台需要的是
**按 items 组织**的内容包契约（见 `openspec/specs/...` 与 change 的 design §2）。
两条路径各写一份规划逻辑，就会出现两套提示词、两套解析、两套失败语义。

本模块把这段能力提取为**一个**规划器：

- `plan_platform_outlines()` —— 平台模板驱动的大纲规划（等价于原
  `outline_service.generate_outline` 的行为，供 `/images/generate-outline` 复用）
- `platform_outlines_to_package()` —— 把平台大纲**转换**为内容包契约（items 化），
  使内容包路径不必另写一套 LLM 调用

`outline_service.generate_outline` 保留为薄封装，响应形状逐字段不变。

不在这里做的事
--------------
- 不调用生图：批量生图仍在 `outline_service.batch_generate_images`（它已负责 Asset Hub
  入库与谱系）。规划与生成分离，便于两者各自被复用。
- 不做 JSON-first 的内容包规划（那条路在 `creative_project/service.py`，形态不同，
  依赖项目与 profile 校验）；本模块只提供**模板驱动**这一路。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

from sqlmodel import select

from app.db.models.platform_template import PlatformTemplate
from app.services.ai.types import LLMMessage

logger = logging.getLogger("ylcraft.ai.content_package_planner")

# 内容包 item 的固定键序（契约见 design §2）。集中定义，避免转换处各写一份而漂移。
ITEM_KEYS = (
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


class ContentPackagePlanner:
    """主题 → 结构化大纲 / 内容包的可复用规划器。"""

    def __init__(self, manager: Any = None):
        """``manager`` 为兼容测试可注入；默认懒取进程级 AI 服务单例。"""
        self._manager = manager

    @property
    def manager(self) -> Any:
        if self._manager is None:
            from app.services.ai import get_ai_service

            self._manager = get_ai_service()
        return self._manager

    # ------------------------------------------------------------------
    # 纯函数部分（无 IO，可单测）
    # ------------------------------------------------------------------

    @staticmethod
    def parse_structured_text(text: str) -> dict:
        """解析 LLM 返回的大纲文本为结构化数据。

        支持格式：
        - 【标题】：xxx
        - 【文案】：xxx（可选，用于小红书等平台的完整文案/话题标签）
        - 【图片提示词】：[封面] xxx <page> 【图片提示词】：[内容] xxx

        原实现位于 `outline_service._parse_outline_text`，此处逐行等价迁移。
        """
        logger.info("[Planner] 开始解析, 输入文本长度: %s", len(text))
        logger.debug("[Planner] 原始文本: %s", text[:500])

        result: dict[str, Any] = {"title": "", "copywriting": "", "pages": []}

        title_match = re.search(r"【标题】[:：]?\s*(.+?)(?:\n|【|$)", text, re.DOTALL)
        if title_match:
            result["title"] = title_match.group(1).strip()
            logger.info("[Planner] 提取到标题: %s", result["title"])

        copywriting_match = re.search(r"【文案】[:：]?\s*(.+?)(?:\n\s*【|$)", text, re.DOTALL)
        if copywriting_match:
            result["copywriting"] = copywriting_match.group(1).strip()
            logger.info("[Planner] 提取到文案: %s", result["copywriting"][:100])

        pages_raw = re.split(r"【图片(?:提示词|说明词)】[:：]?", text)
        logger.info("[Planner] 分割到 %s 个部分", len(pages_raw))

        for part in pages_raw[1:]:  # 跳过第一个（在第一个【图片...】之前的内容）
            part = part.strip()
            if not part:
                continue

            type_match = re.match(r"\[(.+?)\]", part)
            page_type = type_match.group(1) if type_match else "内容"

            prompt = re.sub(r"^\[.+?\]\s*", "", part)
            prompt = re.split(r"\n\s*<page>", prompt)[0].strip()
            prompt = re.split(r"\n\s*---", prompt)[0].strip()

            if prompt:
                logger.info("[Planner] 添加页面: type=%s, prompt_len=%s", page_type, len(prompt))
                result["pages"].append({"type": page_type, "prompt": prompt})

        logger.info("[Planner] 解析完成, 总页数: %s", len(result["pages"]))
        return result

    @staticmethod
    def render_template_prompt(template: Any, topic: str) -> str:
        """把平台模板的 `outline_template` 渲染成 system prompt。"""
        page_structure_json = (
            json.dumps(template.page_structure, ensure_ascii=False) if template.page_structure else ""
        )
        return template.outline_template.format(topic=topic, page_structure=page_structure_json)

    @staticmethod
    def build_outline_messages(system_prompt: str, reference_images: Optional[list[str]]) -> list[LLMMessage]:
        """构造消息；有参考图时用多模态 content 数组，否则纯文本。

        多模态格式：``[{"type": "text", ...}, {"type": "image_url", "image_url": {"url": ...}}]``
        """
        if reference_images:
            content: list[dict[str, Any]] = [{"type": "text", "text": system_prompt}]
            for img in reference_images:
                content.append({"type": "image_url", "image_url": {"url": img}})
            return [LLMMessage(role="user", content=content)]
        return [LLMMessage(role="user", content=system_prompt)]

    @staticmethod
    def platform_outlines_to_package(
        outlines: dict[str, Any],
        *,
        package_type: str = "page_book",
        topic: str = "",
        brief: str = "",
    ) -> dict[str, Any]:
        """把按平台聚合的大纲**转换**为内容包契约。

        规则：
        - 一个平台的一页 ⇒ 一个 item（`items` 是最小可重跑单元）
        - `title` 取页类型，`image_prompt` 取页提示词，`text` 留空（需正文时由后续规划补）
        - `source_refs` 记录来源平台，便于回溯"这一项来自哪个平台的大纲"
        - 规划失败的平台不伪造 item，而是进 `warnings`（不静默吞掉）
        """
        items: list[dict[str, Any]] = []
        warnings: list[str] = []
        index = 0

        for platform, outline in (outlines or {}).items():
            if outline.get("error"):
                warnings.append("平台 %s 规划失败：%s" % (platform, outline.get("error")))
            for page in outline.get("pages") or []:
                index += 1
                items.append(
                    {
                        "index": index,
                        "title": str(page.get("type") or "").strip(),
                        "text": "",
                        "fact": "",
                        "source": "",
                        "source_url": "",
                        "image_prompt": str(page.get("prompt") or "").strip(),
                        "video_prompt": "",
                        "source_refs": [{"platform": platform}],
                        "asset_ids": [],
                        "status": "draft",
                    }
                )

        first = next(iter((outlines or {}).values()), {})
        return {
            "package_type": package_type,
            "title": str(first.get("title") or topic or "").strip(),
            "topic": topic,
            "brief": brief or str(first.get("copywriting") or ""),
            "items": items,
            "outputs": [],
            "source_context": {"platforms": list((outlines or {}).keys())},
            "version": 1,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # 平台模板驱动的大纲规划（有 IO）
    # ------------------------------------------------------------------

    async def plan_platform_outlines(
        self,
        session: Any,
        topic: str,
        platforms: list[str],
        backend_name: Optional[str] = None,
        model: Optional[str] = None,
        reference_images: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """为一个主题生成多平台结构化大纲。

        返回 ``{platform: {title, copywriting, pages: [{type, prompt}], platform,
        platform_name}}``；无可用模板时返回空字典。**行为与响应形状与原
        `outline_service.generate_outline` 完全一致**（含逐平台失败时的兜底结构）。
        """
        logger.info(
            "[Planner] plan_platform_outlines: topic=%s, platforms=%s, backend_name=%s, model=%s",
            topic, platforms, backend_name, model,
        )

        stmt = (
            select(PlatformTemplate)
            .where(
                PlatformTemplate.platform.in_(platforms),
                PlatformTemplate.is_active == True,  # noqa: E712 - 与既有查询保持一致
            )
            .order_by(PlatformTemplate.sort_order)
        )
        result = await session.execute(stmt)
        templates = result.scalars().all()

        if not templates:
            logger.warning("No active platform templates found for: %s", platforms)
            return {}

        outlines: dict[str, Any] = {}

        async def generate_one(tmpl: Any) -> None:
            try:
                system_prompt = self.render_template_prompt(tmpl, topic)
                messages = self.build_outline_messages(system_prompt, reference_images)
                logger.info("[Planner] Calling LLM with messages: %s", len(messages))
                resp = await self.manager.chat(
                    messages=messages,
                    backend_name=backend_name,
                    model=model,
                )
                if resp and resp.success and resp.content:
                    parsed = self.parse_structured_text(resp.content)
                    parsed["platform"] = tmpl.platform
                    parsed["platform_name"] = tmpl.name
                    outlines[tmpl.platform] = parsed
                    logger.info("Generated outline for %s (%s pages)", tmpl.platform, len(parsed.get("pages", [])))
                else:
                    error_msg = ""
                    if resp and hasattr(resp, "error") and resp.error:
                        error_msg = ": %s" % resp.error
                    logger.warning("LLM returned empty content for platform %s%s", tmpl.platform, error_msg)
                    outlines[tmpl.platform] = {
                        "title": topic,
                        "copywriting": "",
                        "pages": [],
                        "platform": tmpl.platform,
                        "platform_name": tmpl.name,
                        "error": resp.error if resp and hasattr(resp, "error") else None,
                    }
            except Exception as exc:  # noqa: BLE001 - 单平台失败不得影响其它平台
                logger.error("Failed to generate outline for %s: %s", tmpl.platform, exc)
                outlines[tmpl.platform] = {
                    "title": topic,
                    "copywriting": "",
                    "pages": [],
                    "platform": tmpl.platform,
                    "platform_name": tmpl.name,
                    "error": str(exc),
                }

        await asyncio.gather(*[generate_one(tmpl) for tmpl in templates])
        return outlines

    async def plan_package(
        self,
        session: Any,
        topic: str,
        platforms: list[str],
        *,
        package_type: str = "page_book",
        brief: str = "",
        backend_name: Optional[str] = None,
        model: Optional[str] = None,
        reference_images: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """一步产出内容包契约：平台大纲规划 + 转换为 items。

        内容包路径调用它即可复用同一套规划，不必另写 LLM 调用与解析。
        """
        outlines = await self.plan_platform_outlines(
            session,
            topic,
            platforms,
            backend_name=backend_name,
            model=model,
            reference_images=reference_images,
        )
        return self.platform_outlines_to_package(
            outlines,
            package_type=package_type,
            topic=topic,
            brief=brief,
        )
