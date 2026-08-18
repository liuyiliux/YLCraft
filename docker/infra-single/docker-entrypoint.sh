#!/usr/bin/env bash
# YLCraft 单容器 entrypoint
# 同时启动 PostgreSQL（沿用 pgvector 官方 entrypoint 完成初始化）与 Redis。
#
# 容器只有一个 PID 1 进程，这里把 PostgreSQL 放到后台，让 Redis 作为前台主进程，
# 以便容器能正常接收 SIGTERM/SIGINT 并优雅退出。

set -e

# 容器停止时同步关闭后台 PostgreSQL（避免残留子进程）
cleanup() {
    echo "[YLCraft] 收到退出信号，正在关闭 PostgreSQL (PID: ${PG_PID:-none})..."
    if [ -n "${PG_PID:-}" ] && kill -0 "$PG_PID" 2>/dev/null; then
        kill "$PG_PID" 2>/dev/null || true
    fi
}
trap cleanup TERM INT EXIT

# ---------------------------------------------------------------------------
# 1) 初始化并启动 PostgreSQL
#    复用官方 entrypoint 的初始化逻辑（创建用户/数据库、执行 init.sql 等）。
#    官方脚本期望容器命令形如 "postgres" 或自定义 PG 启动命令，
#    我们让它以 "postgres" 作为默认命令在后台运行。
# ---------------------------------------------------------------------------
echo "[YLCraft] 正在启动 PostgreSQL（后台）..."
if [ "$1" = "postgres" ] || [ $# -eq 0 ]; then
    # 交给官方 entrypoint，让它以后台方式拉起 PostgreSQL
    /usr/local/bin/docker-entrypoint.sh postgres &
    PG_PID=$!
else
    # 兼容传入自定义命令的情况
    /usr/local/bin/docker-entrypoint.sh "$@" &
    PG_PID=$!
fi

# 等待 PostgreSQL 就绪
echo "[YLCraft] 等待 PostgreSQL 就绪..."
for i in $(seq 1 60); do
    if pg_isready -U "${POSTGRES_USER:-ylcraft}" >/dev/null 2>&1; then
        echo "[YLCraft] PostgreSQL 已就绪！"
        break
    fi
    sleep 1
done

# ---------------------------------------------------------------------------
# 2) 配置并启动 Redis（前台主进程）
# ---------------------------------------------------------------------------
echo "[YLCraft] 正在启动 Redis（前台）..."
if [ -n "$REDIS_PASSWORD" ]; then
    exec redis-server --requirepass "$REDIS_PASSWORD" --dir /data
else
    exec redis-server --dir /data
fi
