# YLCraft 单容器基础设施镜像
# 将原本双容器（PostgreSQL + Redis）合并为单容器，仅需启动一个服务。
# 基于 pgvector/pgvector:pg16（Debian/Ubuntu 系），在其上安装 Redis，
# 通过自定义 entrypoint 同时启动 PostgreSQL 与 Redis。

FROM pgvector/pgvector:pg16

# 安装 Redis
RUN apt-get update \
    && apt-get install -y --no-install-recommends redis-server \
    && rm -rf /var/lib/apt/lists/*

# 复制自定义 entrypoint：先启动 PostgreSQL（沿用官方 entrypoint），再启动 Redis
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 对外暴露 PostgreSQL 与 Redis 端口
EXPOSE 5432 6379

# 数据卷：PG 数据 + Redis 数据
VOLUME ["/var/lib/postgresql/data", "/data"]

# 使用自定义 entrypoint 作为容器的入口
ENTRYPOINT ["docker-entrypoint.sh"]
