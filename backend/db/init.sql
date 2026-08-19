-- YLCraft 数据库初始化脚本
-- 在 docker-entrypoint-initdb.d/ 中执行，仅在首次启动（空数据卷）时生效
--
-- 注意：这里只创建 PostgreSQL 扩展（vector / uuid-ossp / pg_trgm）。
-- 所有表、枚举类型（ENUM）和索引由 Alembic 迁移统一管理，
-- 不要在 init.sql 里重复创建 ENUM，否则会与 001_initial_schema 迁移冲突
-- （DuplicateObject: type "xxx" already exists）。

-- 扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
