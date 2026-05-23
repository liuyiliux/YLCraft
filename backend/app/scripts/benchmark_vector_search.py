"""
YLCraft — 向量搜索性能基准测试

测试不同数据量级别下的向量搜索性能：
- 1万向量
- 10万向量
- 100万向量

使用方法：
    python -m app.scripts.benchmark_vector_search --scale 10000
    python -m app.scripts.benchmark_vector_search --scale 100000
    python -m app.scripts.benchmark_vector_search --scale 1000000
"""

import argparse
import asyncio
import time
import statistics
import random
import logging
from typing import List
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models.asset_hub import AssetEmbedding, AssetNode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ylcraft.benchmark")


class VectorSearchBenchmark:
    """向量搜索性能基准测试"""
    
    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
    
    async def cleanup_test_data(self):
        """清理测试数据"""
        async with self.async_session() as session:
            await session.execute(
                text("DELETE FROM asset_embeddings WHERE name LIKE 'benchmark_%'")
            )
            await session.commit()
            logger.info("已清理测试数据")
    
    async def insert_test_vectors(self, count: int, dimension: int = 1024):
        """插入测试向量数据"""
        logger.info(f"开始插入 {count} 条测试向量 (维度: {dimension})...")
        
        batch_size = 1000
        batches = (count + batch_size - 1) // batch_size
        
        async with self.async_session() as session:
            for batch_idx in range(batches):
                batch_count = min(batch_size, count - batch_idx * batch_size)
                vectors = []
                
                for i in range(batch_count):
                    # 生成随机向量
                    vector = [random.random() for _ in range(dimension)]
                    vectors.append({
                        'id': str(uuid4()),
                        'asset_node_id': str(uuid4()),
                        'embedding': vector,
                        'embedding_model': 'benchmark_test',
                    })
                
                # 批量插入
                start_time = time.time()
                for vec in vectors:
                    await session.execute(
                        text("""
                            INSERT INTO asset_embeddings (id, asset_node_id, embedding, embedding_model)
                            VALUES (:id, :asset_node_id, :embedding, :embedding_model)
                        """),
                        vec
                    )
                
                await session.commit()
                elapsed = time.time() - start_time
                logger.info(f"批次 {batch_idx + 1}/{batches} 完成 ({batch_count} 条, {elapsed:.2f}s)")
        
        logger.info(f"插入完成，总计 {count} 条向量")
    
    async def benchmark_vector_search(
        self, 
        query_count: int = 100,
        top_k: int = 10
    ) -> dict:
        """执行向量搜索基准测试"""
        logger.info(f"开始基准测试: {query_count} 次查询, top_k={top_k}")
        
        query_vectors = []
        for _ in range(query_count):
            query_vectors.append([random.random() for _ in range(1024)])
        
        results = {
            'total_time': 0,
            'query_times': [],
            'qps': 0,
            'avg_time': 0,
            'p50_time': 0,
            'p95_time': 0,
            'p99_time': 0,
        }
        
        start_time = time.time()
        
        for i, query_vector in enumerate(query_vectors):
            query_start = time.time()
            
            async with self.async_session() as session:
                result = await session.execute(
                    text("""
                        SELECT id, asset_node_id, 1 - (embedding <=> :query_vector) as similarity
                        FROM asset_embeddings
                        ORDER BY embedding <=> :query_vector
                        LIMIT :top_k
                    """),
                    {'query_vector': query_vector, 'top_k': top_k}
                )
                rows = result.fetchall()
            
            query_time = (time.time() - query_start) * 1000  # 转换为毫秒
            results['query_times'].append(query_time)
            
            if (i + 1) % 10 == 0:
                logger.info(f"进度: {i + 1}/{query_count} 查询完成")
        
        results['total_time'] = time.time() - start_time
        results['qps'] = query_count / results['total_time']
        results['avg_time'] = statistics.mean(results['query_times'])
        results['p50_time'] = statistics.median(results['query_times'])
        results['p95_time'] = statistics.quantiles(results['query_times'], n=20)[18]  # 95th percentile
        results['p99_time'] = statistics.quantiles(results['query_times'], n=100)[98]  # 99th percentile
        
        return results
    
    async def run(self, scale: int, query_count: int = 100):
        """运行完整基准测试"""
        logger.info(f"=" * 60)
        logger.info(f"向量搜索性能基准测试")
        logger.info(f"数据规模: {scale:,} 向量")
        logger.info(f"查询数量: {query_count}")
        logger.info(f"=" * 60)
        
        # 插入测试数据
        await self.insert_test_vectors(scale)
        
        # 执行基准测试
        results = await self.benchmark_vector_search(query_count)
        
        # 输出结果
        logger.info(f"\n{'=' * 60}")
        logger.info(f"基准测试结果")
        logger.info(f"{'=' * 60}")
        logger.info(f"总耗时:        {results['total_time']:.2f}s")
        logger.info(f"QPS:           {results['qps']:.2f} 查询/秒")
        logger.info(f"平均延迟:      {results['avg_time']:.2f}ms")
        logger.info(f"P50 延迟:      {results['p50_time']:.2f}ms")
        logger.info(f"P95 延迟:      {results['p95_time']:.2f}ms")
        logger.info(f"P99 延迟:      {results['p99_time']:.2f}ms")
        logger.info(f"{'=' * 60}")
        
        # 清理测试数据
        await self.cleanup_test_data()
        
        return results


async def main():
    parser = argparse.ArgumentParser(description='向量搜索性能基准测试')
    parser.add_argument(
        '--scale', 
        type=int, 
        default=10000,
        choices=[10000, 100000, 1000000],
        help='测试数据规模 (10000, 100000, 1000000)'
    )
    parser.add_argument(
        '--queries', 
        type=int, 
        default=100,
        help='查询数量'
    )
    parser.add_argument(
        '--database-url',
        type=str,
        default=settings.DATABASE_URL,
        help='数据库连接 URL'
    )
    
    args = parser.parse_args()
    
    benchmark = VectorSearchBenchmark(args.database_url)
    await benchmark.run(args.scale, args.queries)


if __name__ == '__main__':
    asyncio.run(main())
