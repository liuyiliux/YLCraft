-- YLCraft 数据库初始化脚本
-- 在 docker-entrypoint-initdb.d/ 中执行，仅在首次启动（空数据卷）时生效

-- 扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 平台类型枚举（与 SQLModel PlatformType 枚举同步）
-- 注意：如果 001 迁移或 SQLModel.create_all 已经创建了同名枚举，CREATE TYPE 会失败
-- 但 init.sql 只在数据卷为空时执行一次，所以不会冲突
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'platformtype') THEN
        CREATE TYPE platformtype AS ENUM (
            'xhs', 'douyin', 'kuaishou', 'bilibili', 'weibo', 'zhihu',
            'youtube', 'tiktok', 'twitter', 'telegram', 'wechat_mp',
            'openai', 'anthropic', 'minimax', 'google', 'webdav', 's3', 'ftp'
        );
    END IF;
END$$;

-- 认证类型枚举
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'authtype') THEN
        CREATE TYPE authtype AS ENUM ('cookie', 'api_key', 'oauth2', 'password', 'none');
    END IF;
END$$;

-- 连接状态枚举
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'connectionstatus') THEN
        CREATE TYPE connectionstatus AS ENUM ('active', 'expired', 'failed', 'unknown');
    END IF;
END$$;

-- 凭证获取方式枚举
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'acquisitionmethod') THEN
        CREATE TYPE acquisitionmethod AS ENUM ('manual', 'playwright', 'qrcode');
    END IF;
END$$;
