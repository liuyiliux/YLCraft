"""
YLCraft — 中文全文搜索配置

PostgreSQL 中文分词支持配置：
- 使用 pg_jieba 分词器（推荐）
- 使用 zhparser 分词器（可选）

使用方法：
    1. 安装扩展：CREATE EXTENSION pg_jieba;
    2. 运行迁移：alembic upgrade head
    3. 配置搜索服务使用中文分词

安装 pg_jieba（Linux/macOS）：
    git clone https://github.com/jaiminpan/pg_jieba.git
    cd pg_jieba
    make && sudo make install
    
    psql -U postgres -d your_database -c "CREATE EXTENSION pg_jieba;"

安装 zhparser：
    git clone https://github.com/amutu/zhparser.git
    cd zhparser
    make && sudo make install
    
    psql -U postgres -d your_database -c "CREATE EXTENSION zhparser;"
    psql -U postgres -d your_database -c "CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);"
"""

import logging
from typing import Optional, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("ylcraft.chinese_search")


class ChineseSearchConfig:
    """中文全文搜索配置"""
    
    # 支持的分词器
    TOKENIZERS = {
        "jieba": "pg_jieba",
        "zhparser": "zhparser",
        "simple": "simple",  # 默认，不支持中文
    }
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def check_extension_installed(self, extension_name: str) -> bool:
        """检查扩展是否已安装"""
        result = await self.session.execute(
            text("""
                SELECT 1 FROM pg_extension 
                WHERE extname = :extname
            """),
            {"extname": extension_name}
        )
        return result.scalar_one_or_none() is not None
    
    async def install_extension(self, extension_name: str) -> bool:
        """安装扩展"""
        try:
            await self.session.execute(
                text(f"CREATE EXTENSION IF NOT EXISTS {extension_name}")
            )
            await self.session.commit()
            logger.info(f"已安装扩展: {extension_name}")
            return True
        except Exception as e:
            logger.error(f"安装扩展失败 {extension_name}: {e}")
            return False
    
    async def create_chinese_search_config(
        self, 
        config_name: str = "chinese",
        tokenizer: str = "jieba"
    ) -> bool:
        """
        创建中文全文搜索配置
        
        Args:
            config_name: 配置名称
            tokenizer: 分词器名称（jieba 或 zhparser）
        """
        if tokenizer not in self.TOKENIZERS:
            logger.error(f"不支持的分词器: {tokenizer}")
            return False
        
        internal_tokenizer = self.TOKENIZERS[tokenizer]
        
        try:
            # 创建文本搜索配置
            await self.session.execute(
                text(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_ts_config WHERE cfgname = :config_name
                        ) THEN
                            CREATE TEXT SEARCH CONFIGURATION {config_name} (
                                PARSER = {internal_tokenizer}
                            );
                            
                            -- 添加中文停用词
                            ALTER TEXT SEARCH CONFIGURATION {config_name}
                            ADD MAPPING FOR a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p, q, r, s, t, u, v, w, x, y, z
                            WITH simple;
                        END IF;
                    END $$;
                """),
                {"config_name": config_name}
            )
            await self.session.commit()
            
            logger.info(f"已创建中文搜索配置: {config_name} (使用 {tokenizer})")
            return True
        except Exception as e:
            logger.error(f"创建中文搜索配置失败: {e}")
            return False
    
    async def create_search_vector_column(
        self, 
        table_name: str, 
        column_name: str,
        config_name: str = "chinese"
    ) -> bool:
        """
        创建搜索向量列
        
        使用方法：
            ALTER TABLE assets ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (to_tsvector('chinese', coalesce(name, '') || ' ' || coalesce(description, ''))) STORED;
        """
        try:
            await self.session.execute(
                text(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = :table_name 
                            AND column_name = :column_name
                        ) THEN
                            EXECUTE format(
                                'ALTER TABLE %I ADD COLUMN %I tsvector GENERATED ALWAYS AS (to_tsvector(%L, coalesce(name, '''') || '' '' || coalesce(description, ''''))) STORED',
                                :table_name,
                                :column_name,
                                :config_name
                            );
                        END IF;
                    END $$;
                """),
                {
                    "table_name": table_name,
                    "column_name": column_name,
                    "config_name": config_name
                }
            )
            await self.session.commit()
            
            logger.info(f"已创建搜索向量列: {table_name}.{column_name}")
            return True
        except Exception as e:
            logger.error(f"创建搜索向量列失败: {e}")
            return False
    
    async def create_gin_index(
        self, 
        table_name: str, 
        column_name: str
    ) -> bool:
        """
        创建 GIN 索引加速搜索
        """
        index_name = f"idx_{table_name}_{column_name}_gin"
        
        try:
            await self.session.execute(
                text(f"""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name}
                    ON {table_name} USING gin ({column_name})
                """)
            )
            await self.session.commit()
            
            logger.info(f"已创建 GIN 索引: {index_name}")
            return True
        except Exception as e:
            logger.error(f"创建 GIN 索引失败: {e}")
            return False
    
    async def setup_chinese_search(
        self,
        table_name: str = "asset_nodes",
        column_name: str = "search_vector",
        config_name: str = "chinese",
        tokenizer: str = "jieba"
    ) -> dict:
        """
        完整的中文搜索配置流程
        
        Returns:
            配置结果信息
        """
        result = {
            "extension_installed": False,
            "config_created": False,
            "column_created": False,
            "index_created": False,
            "success": False,
        }
        
        # 1. 检查并安装扩展
        extension_name = self.TOKENIZERS.get(tokenizer, "pg_jieba")
        result["extension_installed"] = await self.check_extension_installed(extension_name)
        
        if not result["extension_installed"]:
            result["extension_installed"] = await self.install_extension(extension_name)
        
        if not result["extension_installed"]:
            logger.warning(f"扩展 {extension_name} 未安装，跳过中文搜索配置")
            return result
        
        # 2. 创建搜索配置
        result["config_created"] = await self.create_chinese_search_config(
            config_name=config_name,
            tokenizer=tokenizer
        )
        
        # 3. 创建搜索向量列
        result["column_created"] = await self.create_search_vector_column(
            table_name=table_name,
            column_name=column_name,
            config_name=config_name
        )
        
        # 4. 创建索引
        result["index_created"] = await self.create_gin_index(
            table_name=table_name,
            column_name=column_name
        )
        
        result["success"] = all([
            result["extension_installed"],
            result["config_created"],
            result["column_created"],
            result["index_created"],
        ])
        
        return result
    
    def generate_search_query(
        self, 
        search_term: str, 
        config_name: str = "chinese"
    ) -> str:
        """
        生成中文搜索查询 SQL
        
        使用方法：
            SELECT * FROM asset_nodes 
            WHERE search_vector @@ to_tsquery('chinese', '人工智能')
            ORDER BY ts_rank(search_vector, to_tsquery('chinese', '人工智能')) DESC;
        """
        # 对搜索词进行分词处理
        # 这里只是简单示例，实际应该在后端进行分词
        return f"""
            SELECT *, ts_rank(search_vector, to_tsquery('{config_name}', '{search_term}')) as rank
            FROM asset_nodes
            WHERE search_vector @@ to_tsquery('{config_name}', '{search_term}')
            ORDER BY rank DESC
            LIMIT 20;
        """


async def setup_chinese_search_demo():
    """
    演示中文搜索配置流程
    
    实际使用时应该：
    1. 确保 PostgreSQL 扩展已安装
    2. 运行数据库迁移
    3. 重新构建搜索索引
    """
    from app.db.database import get_async_session
    
    async with get_async_session() as session:
        config = ChineseSearchConfig(session)
        
        # 检查扩展状态
        for tokenizer_name, extension_name in config.TOKENIZERS.items():
            if tokenizer_name == "simple":
                continue
                
            installed = await config.check_extension_installed(extension_name)
            logger.info(f"{extension_name}: {'已安装' if installed else '未安装'}")
            
            if installed:
                # 完整配置
                result = await config.setup_chinese_search(
                    table_name="asset_nodes",
                    tokenizer=tokenizer_name
                )
                
                logger.info(f"中文搜索配置结果: {result}")
                break
