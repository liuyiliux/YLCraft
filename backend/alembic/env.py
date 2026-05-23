"""
Alembic 环境配置
"""
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys

# 添加 backend 目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入 SQLModel metadata
from sqlmodel import SQLModel
from app.db.models.asset_hub import (
    AssetNode, AssetVersion, AssetRepresentation,
    AssetEmbedding, AssetRelation,
    Tag, AssetTagLink, AIModel,
)

# Alembic Config 对象
config = context.config

# 设置数据库 URL
config.set_main_option("sqlalchemy.url", os.getenv(
    "DATABASE_URL",
    "postgresql://ylcraft:ylcraft_dev@localhost:5432/ylcraft"
).replace("+asyncpg", ""))

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置 target_metadata
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """运行离线迁移（生成 SQL 脚本，不连接数据库）"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """运行在线迁移（连接数据库执行迁移）"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
