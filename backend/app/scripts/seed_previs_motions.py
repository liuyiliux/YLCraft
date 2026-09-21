"""
YLCraft — 预演动作资产种子脚本

按 `slug` 幂等灌入内置动作：已存在则更新，不存在则创建。

什么时候需要它：迁移 `044_add_previs_motion_assets` 建表时已经灌过一次，而**迁移不会重跑**，
所以给已有库补新动作（或改过动作数据后刷新）就跑这个脚本。

使用方法：
    python -m app.scripts.seed_previs_motions
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

# 加载 .env 环境变量（与 uvicorn 启动行为一致）
env_path = Path(__file__).resolve().parents[3] / ".env"
if env_path.exists():
    from dotenv import load_dotenv

    load_dotenv(env_path)

from app.db.database import SessionLocal
from app.services.previs.motion_service import seed_default_motions

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("ylcraft.seed_previs_motions")


def main() -> None:
    logger.info("=" * 60)
    logger.info("YLCraft 预演动作资产种子脚本")
    logger.info("=" * 60)
    with SessionLocal() as session:
        stats = seed_default_motions(session)
    logger.info("-" * 60)
    logger.info(f"完成：新增 {stats['created']} 条，更新 {stats['updated']} 条")


def cli() -> None:
    parser = argparse.ArgumentParser(description="灌入内置预演动作（幂等）")
    parser.parse_args()
    main()


if __name__ == "__main__":
    cli()
