"""断点续传 + 批量队列的回归测试（2026-10-01）。

## 本轮做的两件事（用户要 C：单文件 + 批量都要）

### A. 单文件跨进程续传
  · 稳定文件名（md5 而非 `hash()`）
  · `.partial/` 半成品目录
  · `resume_state.json` 任务落盘
  · 平台下载器加 Range 续传

### B. 批量任务队列落盘
  · `batches.json` 批次状态
  · `/download/batches` 提交/查进度/续跑
  · 重启后只跑没成功的

## ⚠️ 本文件守的坑（都是实测踩到的）

  1. `hash()` 跨进程不稳定（随机盐）→ 续传失效
  2. `follow_redirects` 漏开 → 下到重定向页面（90 字节）
  3. `list_batches` 无条件重置 running → 进度永远 0%
  4. `BackgroundTasks` 不调度 → 批次不动
  5. `asyncio.create_task` 不保留引用 → 任务被 GC
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


# =============================================================================
# A1. 文件名必须跨进程稳定
# =============================================================================

def test_file_key_is_stable_across_processes():
    """**关键回归**：文件标识必须**跨进程稳定**。

    ## 为什么（实测踩到）

    原来是 `hash(effective_url) & 0xFFFFFFFF`，而 Python 对 str 的
    `hash()` **带随机盐**（`PYTHONHASHSEED`）：

        $ python -c "print(hash(url))"   → 1561049425
        $ python -c "print(hash(url))"   → 900355450   # 同一 URL！

    **每个进程都不同** → 重启后文件名变了 → yt-dlp 找不到 `.part`
    → 从头下载（这正是断点续传要解决的问题本身）。

    所以这里**真的开两个子进程**对比，不是看代码里写了 md5 就算。
    """
    from app.api.v1.download import _download_file_key

    url = "https://www.bilibili.com/video/BV1xx411c7XD"
    key_here = _download_file_key(url)
    assert key_here, "file_key 不能为空"

    # 真的跑两个子进程，对比结果
    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "from app.api.v1.download import _download_file_key;"
        "print(_download_file_key(r'%s'))" % (str(BACKEND), url)
    )
    py = str(BACKEND / "venv_win" / "Scripts" / "python.exe")
    if not os.path.exists(py):
        py = sys.executable

    outs = []
    for _ in range(2):
        r = subprocess.run(
            [py, "-c", code], capture_output=True, text=True, timeout=120,
            cwd=str(BACKEND), encoding="utf-8", errors="ignore",
        )
        outs.append((r.stdout or "").strip().splitlines()[-1] if r.stdout else "")

    assert outs[0] == outs[1], (
        f"文件标识跨进程不稳定！\n  进程1: {outs[0]}\n  进程2: {outs[1]}\n"
        "断点续传会因此失效（重启后找不到 .part）。"
    )
    assert outs[0] == key_here, "子进程与本进程的结果也应一致"


def test_hash_is_not_used_for_filename():
    """断言**代码**里不再用 `hash()` 做文件名。

    ⚠️ 注释和 docstring 里会写 `hash(effective_url) & 0xFFFFFFFF`
    来说明"原来错在哪"—— 简单按行过滤注释**不够**
    （docstring 不是 `#` 开头）。用 tokenize 按 token 类型过滤。
    """
    import tokenize

    path = BACKEND / "app" / "api" / "v1" / "download.py"
    toks: list[str] = []
    with open(path, encoding="utf-8") as f:
        for tok in tokenize.generate_tokens(f.readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == tokenize.STRING:
                # ⚠️ 丢掉 docstring —— **不能只看列号是否为 0**：
                # 函数内的 docstring 是缩进的（列号 > 0），
                # 所以按 `start[1] == 0` 过滤会漏掉它们
                # （实测踩到：函数级 docstring 里的说明被当成代码）。
                #
                # 判据：这一行去掉前导空白后**以引号开头** = 独占行的字符串
                stripped = tok.line.strip()
                if stripped.startswith(('"""', "'''", '"', "'")):
                    continue
            toks.append(tok.string)
    code = " ".join(toks)

    assert "ytdlp_{hash(" not in code, "还在用 hash() 生成文件名"
    assert "hash(effective_url)" not in code, "还在用 hash(effective_url)"


# =============================================================================
# A2. 平台下载器的断点续传
# =============================================================================

def test_bilibili_downloader_has_range_resume():
    """**关键**：B站下载器要真有 Range 续传 + `.part` + 原子改名。"""
    src = (BACKEND / "app" / "services" / "download" / "platforms"
           / "bilibili.py").read_text(encoding="utf-8")

    assert "Range" in src, "没有 Range 请求 → 无法续传"
    assert ".part" in src, "没有 .part 临时文件 → '存在'≠'完整'"
    assert "206" in src, "没有 206 判定 → 无法区分'续传'与'服务器忽略 Range'"
    assert "os.replace" in src, "没有原子改名 → 可能出现半截成品"


def test_bilibili_handles_cdn_ignoring_range():
    """**关键**：CDN 忽略 Range 时必须从头写。

    ⚠️ 服务器返回 200（不是 206）说明它给了**完整文件** ——
    这时如果还用 `"ab"` 追加，会得到
    "半截旧数据 + 完整新数据" 的**坏文件**（能播但内容错乱）。
    """
    src = (BACKEND / "app" / "services" / "download" / "platforms"
           / "bilibili.py").read_text(encoding="utf-8")
    assert "status_code == 200" in src, "没有处理'CDN 忽略 Range'"
    assert '"ab"' in src and '"wb"' in src, "没有区分追加/覆盖模式"


def test_bilibili_follows_redirects():
    """**回归**：必须开 `follow_redirects`。

    ⚠️ 实测踩到：不开的话 CDN 返回 302 时，会把**重定向页面**
    （几十字节的 HTML）当文件写下来 —— 表现为
    "下载成功但文件只有 90 字节、打不开"。
    """
    src = (BACKEND / "app" / "services" / "download" / "platforms"
           / "bilibili.py").read_text(encoding="utf-8")
    assert "follow_redirects=True" in src, "没开重定向跟随"


def test_downloaders_share_one_implementation():
    """两处下载循环应**共用一份实现**（避免漂移）。

    ⚠️ 原来 `_download_file_simple` 和 `BilibiliDownloader._download_file`
    是**两份几乎一样的循环** —— 修一份必漏另一份。
    """
    src = (BACKEND / "app" / "services" / "download" / "platforms"
           / "bilibili.py").read_text(encoding="utf-8")
    assert "_stream_to_file" in src, "没有抽出共用实现"
    # 两处都该调它
    assert src.count("_stream_to_file(") >= 3, "两处下载应都调 _stream_to_file"


# =============================================================================
# A3. 续传状态落盘
# =============================================================================

def test_resume_state_helpers_exist():
    """要有登记/注销/查询的辅助函数。"""
    from app.api.v1 import download as dl

    for name in ("_register_resumable", "_unregister_resumable",
                 "_load_resume_state", "_save_resume_state",
                 "_partial_size_for", "partial_dir"):
        assert hasattr(dl, name), f"缺少 {name}"


def test_partial_dir_is_hidden_subdir():
    """半成品放 `<下载目录>/.partial/`（不是混在成品里）。"""
    from app.api.v1.download import partial_dir

    with tempfile.TemporaryDirectory() as tmp:
        d = partial_dir(Path(tmp))
        assert d.name == ".partial"
        assert d.exists()


def test_success_unregisters_but_failure_keeps():
    """**关键**：成功要注销，失败要**保留**（才能续传）。

    ⚠️ 只成功时注销 —— 失败也注销的话就永远无法续传了。
    """
    src = (BACKEND / "app" / "api" / "v1" / "download.py").read_text(encoding="utf-8")

    # 成功路径有注销
    assert "_unregister_resumable(task.task_id)" in src
    # 失败路径**没有**注销（靠"没有 .part 就不列出"来过滤）
    idx = src.find("except Exception as e:")
    assert idx > 0
    tail = src[idx:idx + 900]
    assert "_unregister_resumable" not in tail, (
        "失败路径不该注销 —— 否则无法续传"
    )


def test_resumable_endpoint_flags_no_data():
    """**关键**：没有已下载数据时要标 `can_resume=false`。

    ⚠️ 此时"续传"等于"重下"，不能假装能续
    （用户会以为省了流量，其实没有）。
    """
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.list_resumable)
    assert "can_resume" in src
    assert "done > 0" in src or "can_resume\": done" in src


# =============================================================================
# B. 批量队列
# =============================================================================

def test_batch_store_roundtrip():
    """批量队列：建批次 → 读回 → 更新状态。"""
    from app.api.v1 import download_batch as store

    with tempfile.TemporaryDirectory() as tmp:
        # 把状态文件指到临时目录
        orig = store._batches_path
        store._batches_path = lambda: Path(tmp) / "batches.json"
        try:
            bid = store.create_batch(
                [{"url": "https://a", "title": "a"},
                 {"url": "https://b", "title": "b"}],
                title="测试批次",
            )
            assert bid.startswith("batch_")

            b = store.get_batch(bid)
            assert b and len(b["items"]) == 2

            rows = store.list_batches()
            row = next(r for r in rows if r["batch_id"] == bid)
            assert row["total"] == 2
            assert row["done"] == 0
            assert row["counts"].get("pending") == 2

            store.update_item(bid, 0, status=store.ITEM_DONE)
            rows = store.list_batches()
            row = next(r for r in rows if r["batch_id"] == bid)
            assert row["done"] == 1
            assert row["progress"] == 50.0
        finally:
            store._batches_path = orig


def test_batch_empty_url_rejected():
    """空 URL 的条目要被丢弃（不是建一个永远失败的任务）。"""
    from app.api.v1 import download_batch as store

    with tempfile.TemporaryDirectory() as tmp:
        orig = store._batches_path
        store._batches_path = lambda: Path(tmp) / "batches.json"
        try:
            bid = store.create_batch(
                [{"url": "", "title": "空"}, {"url": "https://x", "title": "有效"}],
            )
            b = store.get_batch(bid)
            assert len(b["items"]) == 1, "空 URL 应被丢弃"
        finally:
            store._batches_path = orig


def test_pending_items_excludes_done():
    """**关键**：续跑只包含 pending/failed，**不含 done**。

    ⚠️ 含 done 的话，"续跑"会把已下好的**再下一遍**
    （浪费流量 + 可能覆盖文件）—— 这正是批量队列要解决的问题。
    """
    from app.api.v1 import download_batch as store

    with tempfile.TemporaryDirectory() as tmp:
        orig = store._batches_path
        store._batches_path = lambda: Path(tmp) / "batches.json"
        try:
            bid = store.create_batch([{"url": f"https://x{i}"} for i in range(4)])
            store.update_item(bid, 0, status=store.ITEM_DONE)
            store.update_item(bid, 1, status=store.ITEM_SKIPPED)
            store.update_item(bid, 2, status=store.ITEM_FAILED)

            pend = store.pending_items(bid)
            idxs = {it["index"] for it in pend}
            assert 0 not in idxs, "done 不该出现在待跑列表"
            assert 1 not in idxs, "skipped 不该出现在待跑列表"
            assert 2 in idxs, "failed 应重试"
            assert 3 in idxs, "pending 应跑"
        finally:
            store._batches_path = orig


def test_batch_resets_stale_running_only():
    """**关键回归**：只重置**上个进程**残留的 running。

    ## 踩坑经过（值得记下来）

    原来 `list_batches()` **无条件**把 running 重置为 pending ——
    本意是修"重启后残留的假状态"，但**无法区分**：

        · 上次进程崩了留下的 running     → 该重置 ✅
        · **当前进程正在下载**的 running  → **不该重置** ❌

    而前端要**轮询** `list_batches()` 看进度 → 真实的"正在下载"
    被每次轮询打回 pending → **进度永远显示 0%**。

    修法：记 `_PROCESS_START`，只重置 `running_since < 进程启动时间` 的。
    """
    from app.api.v1 import download_batch as store

    assert hasattr(store, "_PROCESS_START"), "缺少进程启动时间标记"

    with tempfile.TemporaryDirectory() as tmp:
        orig = store._batches_path
        store._batches_path = lambda: Path(tmp) / "batches.json"
        try:
            bid = store.create_batch([{"url": "https://x"}])

            # 模拟"本进程正在跑"（running_since = 现在）
            store.update_item(bid, 0, status=store.ITEM_RUNNING)
            store.list_batches()
            b = store.get_batch(bid)
            assert b["items"][0]["status"] == store.ITEM_RUNNING, (
                "**本进程正在跑的** running 被误重置了 —— 进度会永远 0%"
            )

            # 模拟"上个进程残留"（running_since 设为很早以前）
            import json as _json

            p = store._batches_path()
            data = _json.loads(p.read_text(encoding="utf-8"))
            data[bid]["items"][0]["running_since"] = store._PROCESS_START - 9999
            p.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

            store.list_batches()
            b = store.get_batch(bid)
            assert b["items"][0]["status"] == store.ITEM_PENDING, (
                "上个进程残留的 running 应该被重置为 pending"
            )
        finally:
            store._batches_path = orig


def test_batch_routes_exist():
    """三个端点都要有。"""
    from app.api.v1 import download_batch_routes as routes

    src = inspect.getsource(routes)
    assert '@router.post("/batches"' in src, "缺提交端点"
    assert '@router.get("/batches"' in src, "缺列表端点"
    assert "/resume" in src, "缺续跑端点"


def test_batch_create_starts_downloading():
    """**关键回归**：提交批次要**立刻开始跑**。

    ⚠️ 原来只创建批次、不启动 —— 用户提交后进度永远是 0%，
    必须再手动调一次 resume 才开始（实测踩到）。

    而且用 `BackgroundTasks` 也不行：它的生命周期绑在**那一个请求**上，
    对"跑几小时"的批次不合适（实测任务没被调度）。
    """
    from app.api.v1 import download_batch_routes as routes

    src = inspect.getsource(routes.create_batch)
    assert "create_task" in src, "提交后要立刻起后台任务"
    assert "_RUNNING_BATCHES" in src, (
        "要保留 task 强引用 —— asyncio 的 task 没引用会被 GC"
    )


def test_run_batch_does_not_call_route_function():
    """**回归**：后台跑批次时不能直接调 `create_download_task`。

    ⚠️ 它是 **FastAPI 路由函数**，参数是 `TaskCreateRequest` + `principal`
    （依赖注入）—— 直接 await 调用签名不匹配，异常被后台任务吞掉，
    表现为"批次一直 0% 进度"（实测踩到）。
    """
    from app.api.v1 import download_batch_routes as routes

    src = inspect.getsource(routes._run_batch)
    assert "DownloadTask" in src, "应直接构造 DownloadTask"
    assert "_run_download_task" in src, "应调真正的执行逻辑"
    assert "create_download_task(" not in src, "不该调路由函数"


def test_batch_item_status_marks_running_since():
    """`update_item` 设 running 时要记 `running_since`（否则无法区分残留）。"""
    from app.api.v1 import download_batch as store

    src = inspect.getsource(store.update_item)
    assert "running_since" in src


def test_delete_batch_keeps_files_by_default():
    """**关键**：删批次记录**默认不删文件**。

    ⚠️ 已下好的文件是用户的成果 —— 不该因为"清理记录"而丢失。
    要删文件必须显式传 `delete_files=true`。
    """
    from app.api.v1 import download_batch_routes as routes

    src = inspect.getsource(routes.delete_batch)
    assert "delete_files" in src
    assert "文件保留" in src or "delete_files=true" in src


# =============================================================================
# 前端接线
# =============================================================================

def _crawler_src() -> str:
    p = BACKEND.parent / "frontend" / "src" / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


def test_frontend_wires_batch_download():
    """**关键回归**：前端要**真的接上**批量下载。

    ⚠️ 本仓库反复踩过的坑：**后端实现了但前端没接**
    （X、快手、YouTube/Telegram、微博、抖音/小红书体检都犯过）。
    后端接口做好只是"能做"，没 UI 入口等于没做。

    这里断言前端确实调了那三个接口。
    """
    src = _crawler_src()
    assert "createDownloadBatch" in src, "没有提交批量的调用"
    assert "listDownloadBatches" in src, "没有查进度的调用"
    assert "resumeDownloadBatch" in src, "没有续跑的调用"


def test_frontend_batch_has_progress_ui():
    """要有进度 UI（否则用户看不到下载到哪了）。"""
    src = _crawler_src()
    assert "batchPanelOpen" in src, "没有进度面板"
    assert "batchList" in src, "没有批次列表状态"
    # 进度条
    assert "percent={b.progress}" in src or "b.progress" in src


def test_frontend_batch_polls_progress():
    """要有轮询（否则进度不会自己刷新）。

    ⚠️ 并且**全部完成时要停**（避免无意义的持续轮询）。
    """
    src = _crawler_src()
    assert "batchPolling" in src, "没有轮询状态"
    assert "setInterval" in src
    assert "clearInterval" in src, "没有清理定时器"
    assert "setBatchPolling(false)" in src, "完成后要停止轮询"


def test_frontend_excludes_wechat_from_batch():
    """微信文章要**排除**在批量下载外（它有专属按钮 + 格式选项）。

    ⚠️ 混在一起会让用户以为能选格式，实际走的是通用路径。
    """
    src = _crawler_src()
    # handleBatchDownload 里要过滤 wechat_mp
    i = src.find("const handleBatchDownload")
    assert i != -1
    seg = src[i:i + 1200]
    assert "wechat_mp" in seg, "handleBatchDownload 没排除微信文章"


def test_frontend_explains_delete_keeps_files():
    """UI 要说明"移除记录不删文件"。

    ⚠️ 不说的话用户会以为文件也没了，不敢点。
    """
    src = _crawler_src()
    assert "只删任务记录" in src or "文件会保留" in src
