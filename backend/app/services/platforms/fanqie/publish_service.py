"""
YLCraft — 番茄小说发布服务（创作项目闭环）

把「创作项目某章 novel_body 正文」推送到番茄作家后台草稿/发布，
并记录章节 ↔ 番茄 item_id 的映射（ProjectPublishRecord），防止重复覆盖。

关键护栏：
  - 番茄建书/建卷/建章节不在 YLCraft 内完成，item_id 必须由用户先在 Web 端建好。
  - 每章只推送一次（绝不静默重试）；失败即记录 error_message 并回执。
  - cookie 来自 PlatformConnection.cookie_content（Netscape），FanqieClient 自动归一化。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import select

from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.creative_project import (
    CreativeProject,
    ProjectContent,
    ProjectPublishRecord,
)
from app.db.models.platform_connection import PlatformConnection, PlatformType
from app.services.platforms.fanqie.client import FanqieClient
from app.services.platforms.fanqie.utils import (
    CookieExpiredError,
    FanqieError,
    ParamError,
    markdown_to_fanqie_html,
)
from app.services.platforms.types import ClientConfig, ClientMode

logger = logging.getLogger("ylcraft.platforms.fanqie.publish")

NOVEL_BODY_TYPE = "novel_body"
FANQIE_SETTINGS_KEY = "fanqie"


def _loads_json(text: str) -> dict:
    try:
        data = json.loads(text or "{}")
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _dumps_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


class FanqiePublishService:
    """创作项目 → 番茄发布编排（异步）。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # =========================================================================
    # 项目番茄绑定（存于 CreativeProject.settings_json.fanqie）
    # =========================================================================

    async def get_binding(self, project_id: str) -> Dict[str, Any]:
        """读取项目番茄绑定 {conn_id, book_id, volume_id, volume_name}。"""
        project = await self.session.get(CreativeProject, project_id)
        if not project:
            return {}
        settings = _loads_json(project.settings_json)
        return settings.get(FANQIE_SETTINGS_KEY, {}) or {}

    async def set_binding(
        self,
        project_id: str,
        *,
        conn_id: str,
        book_id: str,
        volume_id: str,
        volume_name: str,
    ) -> Dict[str, Any]:
        """写入 / 覆盖项目番茄绑定。"""
        project = await self.session.get(CreativeProject, project_id)
        if not project:
            raise ValueError("创作项目不存在")
        connection = await self.session.get(PlatformConnection, conn_id)
        if not connection or connection.platform != PlatformType.FANQIE:
            raise ValueError("conn_id 必须引用已配置的番茄平台连接")
        settings = _loads_json(project.settings_json)
        settings[FANQIE_SETTINGS_KEY] = {
            "conn_id": conn_id,
            "book_id": book_id,
            "volume_id": volume_id,
            "volume_name": volume_name,
        }
        project.settings_json = _dumps_json(settings)
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return settings[FANQIE_SETTINGS_KEY]

    async def preview_chapter(
        self,
        *,
        project_id: str,
        content_id: str,
        item_id: str = "",
        conn_id: str = "",
        book_id: str = "",
        volume_id: str = "",
        volume_name: str = "",
    ) -> Dict[str, Any]:
        """Validate one project chapter and its Fanqie target without writing.

        This is intentionally local-only.  It proves that the selected content
        is a usable ``novel_body`` and resolves project binding overrides. It
        verifies only connection metadata (id/platform), never probes Fanqie,
        exposes, or uses a cookie value.
        """
        binding = await self.get_binding(project_id)
        content = await self.session.get(ProjectContent, content_id)
        target = {
            "conn_id": conn_id or binding.get("conn_id", ""),
            "book_id": book_id or binding.get("book_id", ""),
            "volume_id": volume_id or binding.get("volume_id", ""),
            "volume_name": volume_name or binding.get("volume_name", ""),
            "item_id": item_id,
        }
        missing: list[str] = []
        if not content or content.project_id != project_id:
            missing.append("valid novel_body content_id for this project")
        elif content.content_type != NOVEL_BODY_TYPE:
            missing.append("content_id with content_type=novel_body")
        elif not (content.text_content or "").strip():
            missing.append("non-empty novel_body text")
        for field in ("conn_id", "book_id", "volume_id", "item_id"):
            if not target[field]:
                missing.append(field)
        connection = None
        if target["conn_id"]:
            connection = await self.session.get(PlatformConnection, target["conn_id"])
            if not connection or connection.platform != PlatformType.FANQIE:
                missing.append("conn_id referencing a configured fanqie connection")
        return {
            "ready": not missing,
            "missing": missing,
            "resolved_target": target,
            "connection": {
                "exists": bool(connection),
                "platform": connection.platform.value if connection else "",
                "status": connection.status.value if connection else "",
            },
            "chapter": {
                "content_id": content_id,
                "title": content.title if content else "",
                "chapter_number": content.chapter_number if content else None,
                "content_type": content.content_type if content else "",
                "text_length": len(content.text_content or "") if content else 0,
            },
        }

    # =========================================================================
    # 发布单章
    # =========================================================================

    async def publish_chapter(
        self,
        *,
        project_id: str,
        content_id: str,
        conn_id: str,
        book_id: str,
        volume_id: str,
        volume_name: str,
        item_id: str,
        action: str = "draft",
        chapter_number: Optional[int] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        把某章 novel_body 正文保存到番茄草稿。

        约定：
          - action="draft" 是当前唯一支持动作；正式发布尚未实现。
          - 每章只推送一次，不静默重试；失败抛异常并由调用方记录。

        Returns:
            序列化后的 ProjectPublishRecord 字典。

        Raises:
            ValueError（参数/正文校验）、CookieExpiredError / ParamError / FanqieError（番茄侧）。
        """
        if action != "draft":
            raise ValueError("当前仅支持保存番茄草稿（action=draft），正式发布尚未实现")
        missing_target = [
            field
            for field, value in (("conn_id", conn_id), ("book_id", book_id), ("volume_id", volume_id), ("item_id", item_id))
            if not str(value or "").strip()
        ]
        if missing_target:
            raise ValueError(f"保存番茄草稿缺少目标参数：{', '.join(missing_target)}")

        # 1. 校验正文
        content = await self.session.get(ProjectContent, content_id)
        if not content or content.project_id != project_id:
            raise ValueError("章节正文不存在或不属于该项目")
        if content.content_type != NOVEL_BODY_TYPE:
            raise ValueError(f"仅 novel_body 正文可保存到番茄草稿（当前类型：{content.content_type}）")
        if not (content.text_content or "").strip():
            raise ValueError("正文为空，无法发布")

        # 2. 校验凭证
        conn = await self.session.get(PlatformConnection, conn_id)
        if not conn or conn.platform != PlatformType.FANQIE:
            raise ValueError("conn_id 必须引用已配置的番茄平台连接")
        if not conn.cookie_content:
            raise ValueError("番茄凭证缺失（PlatformConnection 未配置 cookie）")

        chapter_no = chapter_number if chapter_number is not None else content.chapter_number
        chapter_title = title or content.title or (f"第{chapter_no}章" if chapter_no else "未命名章节")

        # 3. 预建记录（pending）
        record = ProjectPublishRecord(
            project_id=project_id,
            content_id=content_id,
            conn_id=conn_id,
            book_id=str(book_id),
            item_id=str(item_id),
            volume_id=str(volume_id),
            volume_name=volume_name or "",
            chapter_number=chapter_no,
            action=action,
            status="pending",
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)

        # 4. 调用番茄（每条只试一次）
        config = ClientConfig(platform="fanqie", mode=ClientMode.API, cookie=conn.cookie_content)
        try:
            async with FanqieClient(config) as client:
                data = await client.save_draft(
                    book_id=str(book_id),
                    item_id=str(item_id),
                    title=chapter_title,
                    content_html=markdown_to_fanqie_html(content.text_content),
                    volume_name=volume_name or "",
                    volume_id=str(volume_id),
                )
            record.remote_version = data.get("latest_version")
            record.status = "success"
            record.post_url = data.get("url") or ""
            record.error_message = ""
            conn.success_count = (conn.success_count or 0) + 1
            conn.last_used = datetime.now()
            conn.status = "active"
        except (CookieExpiredError, ParamError, FanqieError) as e:
            record.status = "failed"
            record.error_message = str(e)
            conn.fail_count = (conn.fail_count or 0) + 1
            conn.error_message = str(e)[:500]
            # 失败时同样提交记录，便于前端排查；异常向上抛交由路由转 HTTP 错误
            await self.session.commit()
            await self.session.refresh(record)
            raise
        finally:
            await self.session.commit()

        await self.session.refresh(record)
        return self._serialize(record)

    # =========================================================================
    # 批量发布
    # =========================================================================

    async def publish_chapters_bulk(
        self,
        *,
        project_id: str,
        conn_id: str,
        book_id: str,
        volume_id: str,
        volume_name: str,
        items: List[Dict[str, Any]],
        action: str = "draft",
    ) -> List[Dict[str, Any]]:
        """
        批量发布多章。

        items: [{"content_id", "item_id", "chapter_number"?, "title"?}, ...]
        每章独立调用 publish_chapter；单章失败不影响其余章节，
        返回逐章结果（含成功/失败状态与 error_message）。
        """
        results: List[Dict[str, Any]] = []
        for item in items:
            try:
                res = await self.publish_chapter(
                    project_id=project_id,
                    content_id=item["content_id"],
                    conn_id=conn_id,
                    book_id=book_id,
                    volume_id=volume_id,
                    volume_name=volume_name,
                    item_id=item["item_id"],
                    action=action,
                    chapter_number=item.get("chapter_number"),
                    title=item.get("title"),
                )
                results.append({"content_id": item["content_id"], "success": True, "record": res})
            except Exception as e:  # noqa: BLE001 — 批量需隔离单章异常
                logger.warning(f"[FanqiePublish] 单章发布失败 content={item.get('content_id')}: {e}")
                results.append({
                    "content_id": item.get("content_id"),
                    "success": False,
                    "error": str(e),
                })
        return results

    # =========================================================================
    # 查询发布状态
    # =========================================================================

    async def get_publish_status(
        self,
        project_id: str,
        chapter_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """查询项目的番茄发布记录（按时间倒序）。"""
        stmt = (
            select(ProjectPublishRecord)
            .where(ProjectPublishRecord.project_id == project_id)
        )
        if chapter_number is not None:
            stmt = stmt.where(ProjectPublishRecord.chapter_number == chapter_number)
        stmt = stmt.order_by(ProjectPublishRecord.created_at.desc())
        rows = (await self.session.exec(stmt)).all()
        return [self._serialize(r) for r in rows]

    # =========================================================================
    # 序列化
    # =========================================================================

    @staticmethod
    def _serialize(record: ProjectPublishRecord) -> Dict[str, Any]:
        return {
            "id": record.id,
            "project_id": record.project_id,
            "content_id": record.content_id,
            "conn_id": record.conn_id,
            "book_id": record.book_id,
            "item_id": record.item_id,
            "volume_id": record.volume_id,
            "volume_name": record.volume_name,
            "chapter_number": record.chapter_number,
            "action": record.action,
            "remote_version": record.remote_version,
            "post_url": record.post_url,
            "status": record.status,
            "error_message": record.error_message,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
