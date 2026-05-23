"""
YLCraft — 向量索引重建脚本

用于重建 pgvector 的 HNSW 索引，提升查询性能。

索引类型：
- IVFFlat: 倒排文件索引，适合插入密集的场景
- HNSW: 分层可导航小世界图，高召回率

使用方法：
    python -m app.scripts.rebuild_vector_index --index-type hnsw
    python -m app.scripts.rebuild_vector_index --index-type ivfflat
    python -m app.scripts.rebuild_vector_index --recreate
"""

import argparse
import asyncio
import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ylcraft.rebuild_index")


class VectorIndexRebuilder:
    """向量索引重建器"""
    
    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
    
    async def get_index_info(self, table_name: str = 'asset_embeddings') -> dict:
        """获取索引信息"""
        async with self.async_session() as session:
            result = await session.execute(
                text("""
                    SELECT 
                        indexname,
                        indexdef
                    FROM pg_indexes
                    WHERE tablename = :table_name
                    AND indexname LIKE '%embedding%'
                """),
                {'table_name': table_name}
            )
            indexes = result.fetchall()
            
            info = {
                'table': table_name,
                'indexes': []
            }
            
            for idx in indexes:
                info['indexes'].append({
                    'name': idx[0],
                    'definition': idx[1]
                })
            
            # 获取表统计信息
            stat_result = await session.execute(
                text("SELECT COUNT(*) FROM :table_name"),
                {'table_name': table_name}
            )
            info['row_count'] = stat_result.scalar()
            
            return info
    
    async def get_embedding_dimension(self) -> int:
        """获取向量维度"""
        async with self.async_session() as session:
            result = await session.execute(
                text("""
                    SELECT 
                        COLLATION_NAME, 
                        TYPDELIM
                    FROM pg_attribute 
                    WHERE attrelid = 'asset_embeddings'::regclass
                    AND attname = 'embedding'
                """)
            )
            # 获取向量维度需要从类型定义中解析
            dim_result = await session.execute(
                text("""
                    SELECT atttypmod - 4 
                    FROM pg_attribute 
                    WHERE attrelid = 'asset_embeddings'::regclass
                    AND attname = 'embedding'
                """)
            )
            dim = dim_result.scalar()
            return dim if dim else 1024  # 默认维度
    
    async def drop_index(self, index_name: str):
        """删除索引"""
        async with self.async_session() as session:
            await session.execute(text(f'DROP INDEX IF EXISTS "{index_name}"'))
            await session.commit()
            logger.info(f"已删除索引: {index_name}")
    
    async def create_hnsw_index(
        self, 
        column: str = 'embedding',
        m: int = 16,
        ef_construction: int = 200
    ):
        """
        创建 HNSW 索引
        
        参数:
            m: 每个节点的最大连接数，越大越精确但越慢
            ef_construction: 构建时的搜索范围，越大越精确但越慢
        """
        logger.info(f"开始创建 HNSW 索引 (m={m}, ef_construction={ef_construction})...")
        
        index_name = f"idx_asset_embeddings_hnsw_{int(time.time())}"
        
        async with self.async_session() as session:
            # 创建 HNSW 索引
            await session.execute(text(f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}"
                ON asset_embeddings 
                USING hnsw ({column} vector_cosine_ops)
                WITH (m = {m}, ef_construction = {ef_construction})
            """))
            await session.commit()
            
            logger.info(f"HNSW 索引创建完成: {index_name}")
            return index_name
    
    async def create_ivfflat_index(
        self, 
        column: str = 'embedding',
        lists: int = 100
    ):
        """
        创建 IVFFlat 索引
        
        参数:
            lists: 聚类数量，越大越精确但越慢
        """
        logger.info(f"开始创建 IVFFlat 索引 (lists={lists})...")
        
        index_name = f"idx_asset_embeddings_ivfflat_{int(time.time())}"
        
        async with self.async_session() as session:
            # 首先创建向量列（如果不存在）
            # IVFFlat 需要先创建
            await session.execute(text(f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}"
                ON asset_embeddings 
                USING ivfflat ({column} vector_cosine_ops)
                WITH (lists = {lists})
            """))
            await session.commit()
            
            logger.info(f"IVFFlat 索引创建完成: {index_name}")
            return index_name
    
    async def set_hnsw_parameters(self, ef_search: int = 100):
        """设置 HNSW 查询参数"""
        # 注意：pgvector 不支持动态调整 HNSW 的 ef_search 参数
        # 需要在查询时设置，或者重建索引
        logger.info(f"HNSW ef_search 参数需要在查询时设置，当前值: {ef_search}")
        logger.info("提示：可以在查询前设置 SET hnsw.ef_search = 100")
    
    async def rebuild_index(
        self, 
        index_type: str = 'hnsw',
        recreate: bool = False,
        m: int = 16,
        ef_construction: int = 200,
        lists: int = 100
    ):
        """重建索引"""
        logger.info(f"{'=' * 60}")
        logger.info(f"开始重建向量索引")
        logger.info(f"索引类型: {index_type.upper()}")
        logger.info(f"{'=' * 60}")
        
        start_time = time.time()
        
        if recreate:
            # 获取现有索引
            index_info = await self.get_index_info()
            
            # 删除现有索引
            for idx in index_info['indexes']:
                await self.drop_index(idx['name'])
                # 等待索引删除完成
                await asyncio.sleep(1)
        
        # 创建新索引
        if index_type.lower() == 'hnsw':
            await self.create_hnsw_index(m=m, ef_construction=ef_construction)
        elif index_type.lower() == 'ivfflat':
            await self.create_ivfflat_index(lists=lists)
        else:
            raise ValueError(f"不支持的索引类型: {index_type}")
        
        elapsed = time.time() - start_time
        
        logger.info(f"\n{'=' * 60}")
        logger.info(f"索引重建完成!")
        logger.info(f"耗时: {elapsed:.2f}秒 ({elapsed/60:.2f}分钟)")
        logger.info(f"{'=' * 60}")
        
        # 输出查询提示
        logger.info(f"\n查询优化提示:")
        logger.info(f"1. HNSW 索引查询性能优化:")
        logger.info(f"   SET hnsw.ef_search = 100  # 数值越大越精确但越慢")
        logger.info(f"2. 常用查询示例:")
        logger.info(f"   SELECT * FROM asset_embeddings")
        logger.info(f"   ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector")
        logger.info(f"   LIMIT 10;")


async def main():
    parser = argparse.ArgumentParser(description='向量索引重建工具')
    parser.add_argument(
        '--index-type',
        type=str,
        default='hnsw',
        choices=['hnsw', 'ivfflat'],
        help='索引类型 (hnsw 或 ivfflat)'
    )
    parser.add_argument(
        '--recreate',
        action='store_true',
        help='重建前删除现有索引'
    )
    parser.add_argument(
        '--m',
        type=int,
        default=16,
        help='HNSW: 每个节点的最大连接数 (默认: 16)'
    )
    parser.add_argument(
        '--ef-construction',
        type=int,
        default=200,
        help='HNSW: 构建时的搜索范围 (默认: 200)'
    )
    parser.add_argument(
        '--lists',
        type=int,
        default=100,
        help='IVFFlat: 聚类数量 (默认: 100)'
    )
    parser.add_argument(
        '--database-url',
        type=str,
        default=settings.DATABASE_URL,
        help='数据库连接 URL'
    )
    parser.add_argument(
        '--info',
        action='store_true',
        help='仅显示索引信息，不进行重建'
    )
    
    args = parser.parse_args()
    
    rebuilder = VectorIndexRebuilder(args.database_url)
    
    if args.info:
        # 仅显示索引信息
        index_info = await rebuilder.get_index_info()
        logger.info(f"\n{'=' * 60}")
        logger.info(f"当前索引信息")
        logger.info(f"{'=' * 60}")
        logger.info(f"表名: {index_info['table']}")
        logger.info(f"行数: {index_info['row_count']}")
        logger.info(f"\n索引列表:")
        for idx in index_info['indexes']:
            logger.info(f"  - {idx['name']}")
            logger.info(f"    {idx['definition']}")
    else:
        # 执行索引重建
        await rebuilder.rebuild_index(
            index_type=args.index_type,
            recreate=args.recreate,
            m=args.m,
            ef_construction=args.ef_construction,
            lists=args.lists
        )


if __name__ == '__main__':
    asyncio.run(main())
