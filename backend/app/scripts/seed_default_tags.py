"""
YLCraft — 默认标签种子脚本

初始化资产中枢的预设标签树。可重复执行（幂等）。

标签树结构：
- 类型        (category=type)
  ├─ 角色
  ├─ 角色立绘
  ├─ 背景
  ├─ 画风
  ├─ 道具
  └─ 场景
- 风格        (category=style)
  ├─ 写实
  ├─ 动漫
  └─ 国风
- 来源        (category=source)
  ├─ AI生成
  ├─ 上传
  └─ 采集
- 状态        (category=status)
  ├─ 草稿
  ├─ 成品
  └─ 已弃用

使用方法：
    python -m app.scripts.seed_default_tags
    python -m app.scripts.seed_default_tags --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Dict, List, Optional

# 加载 .env 环境变量（与 uvicorn 启动行为一致）
from pathlib import Path
env_path = Path(__file__).resolve().parents[3] / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models.asset_hub import Tag

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("ylcraft.seed_tags")


# 预设标签树：(name, category, [(child_name, ...), ...])
DEFAULT_TAG_TREE: List[Dict] = [
    {
        "name": "类型",
        "category": "type",
        "color": "#3b82f6",
        "children": [
            {"name": "角色"},
            {"name": "角色立绘"},
            {"name": "背景"},
            {"name": "画风"},
            {"name": "道具"},
            {"name": "场景"},
            {"name": "分镜"},
            {"name": "漫画页"},
        ],
    },
    {
        "name": "风格",
        "category": "style",
        "color": "#a855f7",
        "children": [
            {"name": "写实"},
            {"name": "动漫"},
            {"name": "国风"},
            {"name": "赛博朋克"},
            {"name": "水墨"},
        ],
    },
    {
        "name": "来源",
        "category": "source",
        "color": "#10b981",
        "children": [
            {"name": "AI生成"},
            {"name": "上传"},
            {"name": "采集"},
            {"name": "解析"},
        ],
    },
    {
        "name": "状态",
        "category": "status",
        "color": "#f59e0b",
        "children": [
            {"name": "草稿"},
            {"name": "成品"},
            {"name": "已弃用"},
        ],
    },
]


async def _find_tag(session: AsyncSession, name: str, parent_id: Optional[str] = None) -> Optional[Tag]:
    """按 name + parent_id 查找标签"""
    stmt = select(Tag).where(Tag.name == name)
    if parent_id is None:
        stmt = stmt.where(Tag.parent_id.is_(None))
    else:
        stmt = stmt.where(Tag.parent_id == parent_id)
    result = await session.execute(stmt.limit(1))
    return result.scalar_one_or_none()


async def _create_tag(
    session: AsyncSession,
    name: str,
    parent_id: Optional[str] = None,
    category: Optional[str] = None,
    color: Optional[str] = None,
) -> Tag:
    """创建单个标签（含路径与 level）"""
    from uuid import uuid4

    level = 0
    path = f"root/{name}"
    if parent_id:
        parent = await session.get(Tag, parent_id)
        if parent:
            level = parent.level + 1
            path = f"{parent.path}/{name}"

    tag = Tag(
        id=str(uuid4()),
        name=name,
        parent_id=parent_id,
        level=level,
        path=path,
        category=category,
        color=color,
        asset_count=0,
    )
    session.add(tag)
    await session.flush()
    await session.refresh(tag)
    return tag


async def _ensure_tag(
    session: AsyncSession,
    name: str,
    parent_id: Optional[str] = None,
    category: Optional[str] = None,
    color: Optional[str] = None,
) -> Tag:
    """幂等获取或创建标签"""
    existing = await _find_tag(session, name, parent_id)
    if existing:
        # 补齐缺失的字段（如已存在但未设 category）
        updated = False
        if category and existing.category != category:
            existing.category = category
            updated = True
        if color and existing.color != color:
            existing.color = color
            updated = True
        if updated:
            await session.flush()
        return existing
    return await _create_tag(session, name, parent_id, category, color)


async def seed_tags(session: AsyncSession, dry_run: bool = False) -> Dict[str, int]:
    """播种默认标签树，返回 {created, skipped} 统计"""
    stats = {"created": 0, "skipped": 0}

    for root_def in DEFAULT_TAG_TREE:
        root_name = root_def["name"]
        root_category = root_def.get("category")
        root_color = root_def.get("color")

        existing = await _find_tag(session, root_name, None)
        if existing:
            stats["skipped"] += 1
            root_tag = existing
        else:
            if dry_run:
                logger.info(f"[DRY-RUN] 将创建根标签: {root_name}")
                stats["created"] += 1
                continue
            root_tag = await _create_tag(session, root_name, None, root_category, root_color)
            stats["created"] += 1
            logger.info(f"创建根标签: {root_name} (category={root_category})")

        # 子标签
        for child_def in root_def.get("children", []):
            child_name = child_def["name"]
            child_existing = await _find_tag(session, child_name, root_tag.id)
            if child_existing:
                stats["skipped"] += 1
                continue
            if dry_run:
                logger.info(f"[DRY-RUN] 将创建子标签: {root_name}/{child_name}")
                stats["created"] += 1
                continue
            await _create_tag(session, child_name, root_tag.id, root_category, root_color)
            stats["created"] += 1
            logger.info(f"  创建子标签: {root_name}/{child_name}")

    return stats


async def main(dry_run: bool = False) -> None:
    """主入口"""
    logger.info("=" * 60)
    logger.info("YLCraft 默认标签种子脚本")
    if dry_run:
        logger.info("[DRY-RUN] 仅打印将创建的标签，不写入数据库")
    logger.info("=" * 60)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            stats = await seed_tags(session, dry_run=dry_run)

    logger.info("-" * 60)
    logger.info(f"完成：新增 {stats['created']} 个，跳过 {stats['skipped']} 个（已存在）")
    if dry_run:
        logger.info("（dry-run 模式未实际写入）")


def cli() -> None:
    parser = argparse.ArgumentParser(description="初始化默认标签树")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))


if __name__ == "__main__":
    cli()
