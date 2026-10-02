"""第二轮审计（2026-10-02）的回归测试。

第一轮见 `test_audit_fixes.py`（UI 可达性）与
`test_audit_data_honesty.py`（数据诚实性）。本文件覆盖第二轮的高危项。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend" / "src"


def _fx(rel: str) -> str:
    p = FRONTEND / rel
    if not p.exists():
        pytest.skip(f"{rel} 不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 假选项：评论排序控件
# =============================================================================

def test_comment_sort_only_for_bili():
    """**关键回归**：评论排序控件**只有 B站显示**。

    ## 假选项的样子

    排序控件（最热/最新/最早）原来**无平台守卫**，但后端 `sort`
    **只传给 B站**的 `get_comments_paged`（其它平台走
    `get_comments_page`，压根不接收 sort）。

    结果：非 B站平台切"最热/最新/最早"**毫无反应** ——
    典型**假选项**（本仓库铁律：假选项比没有更糟）。

    ⚠️ 定位要精确：`label: '最热'` 在**小红书搜索配置**里也出现
    （那是搜索排序，不是评论排序），所以要用 `<Segmented` 锚定。
    """
    src = _fx("pages/crawler/index.tsx")
    # 评论排序控件的锚点：Segmented + 三个选项（最热/最新/最早）
    i = src.find("options={[{ label: '最热', value: 0 }")
    assert i != -1, "找不到评论排序控件的 Segmented"
    # 往前 300 字符应能看到 B站 平台守卫
    head = src[max(0, i - 300):i]
    assert "platform === 'bili'" in head, (
        "评论排序控件没有 B站守卫 —— 其它平台显示但选了没用（假选项）"
    )


# =============================================================================
# 快手详情：不再谎报 404
# =============================================================================

def test_kuaishou_get_detail_not_return_none():
    """**关键**：快手 `get_detail` 不能**永远返回 None**。

    ## 谎报的样子

    原来 `return None`（注释说"搜索结果里已含全部字段，不重新请求"）
    —— 但 `crawler/service.py::get_note_detail` 拿到 None 就
    `return {}`，路由层变成 **404「笔记不存在或获取失败」**。

    **而作品是真实存在的**（用户刚从搜索结果点进来）。

    现在改成参照抖音：优先用调用方传的 `raw` 解析；
    没有 `raw` 时**如实报错**（而不是静默 None）。

    ⚠️ 断言必须过滤注释：修复说明里**故意引用了**
    `原来是 return None`，简单 substring 会把**自己写的修复说明**
    误判成"还没改"。
    """
    import io
    import tokenize

    from app.services.platforms.kuaishou.client import KuaishouClient

    raw_src = inspect.getsource(KuaishouClient.get_detail)
    # 只保留可执行 token（丢掉注释与 docstring）
    toks = []
    for tok in tokenize.generate_tokens(io.StringIO(raw_src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and tok.line.strip().startswith(
            ('"""', "'''", '"', "'")
        ):
            continue
        toks.append(tok.string)
    code = " ".join(toks)

    assert "return None" not in code, (
        "get_detail 仍然会返回 None → 被 service 吞成 404 谎报"
    )
    assert "raw" in code, "应该优先用搜索结果的原始条目"
    assert "ContentNotFoundError" in code, (
        "没有 raw 时应抛可读错误（而不是静默 None）"
    )


def test_kuaishou_detail_parses_photo():
    """快手详情要从 `photo` 字段解析出真实内容（不是空壳）。"""
    from app.services.platforms.kuaishou.client import KuaishouClient

    raw_src = inspect.getsource(KuaishouClient.get_detail)
    for field in ("caption", "author", "coverUrl", "likeCount"):
        assert field in raw_src, f"详情解析缺字段：{field}"


# =============================================================================
# 假选项：单个下载的断点续传入口
# =============================================================================

def test_resumable_downloads_has_ui_entry():
    """**关键回归**：单个下载的断点续传要有 UI 入口。

    ⚠️ 后端 `/download/resumable` 早就实现了、前端 API 也封装好了
    （`listResumableDownloads` / `resumeDownload`），
    但**全仓没有任何调用点** —— 下载中断后用户看不到未完成任务、
    也没有"继续"按钮，只能重新下载。

    而**批量**下载的续传是有 UI 的（采集页），这是能力不一致。
    """
    src = _fx("pages/download/index.tsx")
    assert "listResumableDownloads" in src, (
        "下载页没有调用 listResumableDownloads（单个下载无法续传）"
    )
    assert "resumeDownload" in src, "没有续传调用"
    assert "未完成的下载" in src, "没有'未完成的下载'区块"


def test_resumable_entry_flags_no_data():
    """**关键**：没有已下载数据时要标"续传=重下"（不假装能续）。"""
    src = _fx("pages/download/index.tsx")
    assert "can_resume" in src, "没有按 can_resume 区分"
    assert "无已下载数据" in src or "续传=重下" in src, (
        "没说明'没有已下载数据时续传等同于重下'"
    )


# =============================================================================
# 假选项：微信公众号每页条数
# =============================================================================

def test_wechat_page_size_matches_backend_limit():
    """**回归**：公众号的每页条数选项要≤10（后端封顶）。

    ⚠️ 审计说前端给 20/50/100 但后端 `count=min(page_size, 10)`
    最多 10 条 —— 核实后**前端已经限制到 5/10**（`min()`），
    所以这条是**误报**。测试留着防退化。
    """
    src = _fx("pages/crawler/index.tsx")
    i = src.find("微信公众号后台接口封顶")
    assert i != -1, "找不到公众号每页条数的限制说明"
    seg = src[i:i + 400]
    assert "'5条'" in seg and "'10条'" in seg, (
        "公众号的每页选项应限制在 5/10（后端封顶 10）"
    )
    # 且限制条件存在
    assert "wechat_mp" in seg


# =============================================================================
# 种子恢复的幂等性
# =============================================================================

def _code(src: str) -> str:
    """剥掉注释与 docstring，只留可执行 token。

    ⚠️ 这个文件里几乎每条测试都需要它 ——
    修复说明会**故意引用**旧代码（`原来是 hasattr(...)`、`原来是 return None`），
    不过滤就会把**自己写的修复说明**误判成"还没改"。
    """
    import io
    import tokenize

    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and tok.line.strip().startswith(
            ('"""', "'''", '"', "'")
        ):
            continue
        out.append(tok.string)
    return " ".join(out)


def test_torrent_terminal_states_include_done():
    """**关键回归**：种子终态集合必须含 `done`。

    ## 不幂等的样子

    `models.py::_state_name` 把"上传完成"归一成 **`"done"`**，
    而 `_TERMINAL_STATES` 原来只有
    `{completed, finished, seeding, deleted}` —— **不含 `done`**。

    于是每次启动都会把**已下载完成**的种子重新 add 进引擎并强制
    写成"downloading"：用户看到已下完的种子变成"下载中"，
    且每次开机重复做无用的分片校验。

    教训：这里的字面量必须与 `models.py` 的 `normalized_status`
    **实际产出的值**对齐 —— 两处词汇表漂移是很隐蔽的 bug。
    """
    from app.services.torrent.models import TorrentStatus
    from app.services.torrent.service import TorrentService

    assert "done" in TorrentService._TERMINAL_STATES, (
        "终态集合漏了 'done' —— 已完成的种子每次重启都会被重新拉起"
    )
    # 交叉验证：引擎完成态确实归一成 "done"
    # ⚠️ 产出点是 `TorrentStatus.normalized_status` 属性
    #    （不是 `_state_name` —— 那个返回原始 state）
    st = TorrentStatus(torrent_hash="x", state="uploading")
    assert st.normalized_status == "done", (
        f"引擎完成态归一成 {st.normalized_status!r} 而非 'done' —— "
        "那终态集合要跟着改（这里变了请同步更新 _TERMINAL_STATES）"
    )


# =============================================================================
# 能力判断：用声明不用 hasattr
# =============================================================================

def test_users_me_uses_capabilities_not_hasattr():
    """**关键**：`/users/me` 要用 `capabilities` 判断，**不用 hasattr**。

    `hasattr` 只说明"方法存在"，**不代表实现了**
    （基类里每个平台都有 `get_self_profile`，可能只 raise）。

    而且 `platforms/meta.py` 的设计原则明确写了
    "**能力用声明而非猜测**……而不是让公共代码去 hasattr 或猜名字"
    —— 这里正是违反自己定的规矩。

    ⚠️ 过滤注释：修复说明里**引用了** `hasattr(client, ...)`。
    """
    from app.api.v1 import users

    code = _code(inspect.getsource(users.get_self_profile))
    assert "hasattr" not in code, (
        "/users/me 还在用 hasattr 猜能力 —— 应查 meta.capabilities"
    )
    assert "supports" in code, "应使用 meta.supports()"


def test_users_me_returns_501_not_400():
    """**回归**：功能没做要报 **501**（不是 400）。

    400 听起来像"你参数写错了"，501 才是"这个功能没做"。
    与 `comments.py` 的约定保持一致。
    """
    from app.api.v1 import users

    code = _code(inspect.getsource(users.get_self_profile))
    assert "501" in code, "未实现应报 501（与 comments.py 一致）"


# =============================================================================
# 样式：表格压缩
# =============================================================================

def test_create_time_column_not_vertical():
    """**关键**：发布时间列不能窄到装不下内容（否则表头竖排单字）。

    `formatTime` 的最坏输出是 `toLocaleDateString('zh-CN')`
    =「2026/10/1」≈ 70px，加 antd 单元格左右各 16px padding
    = **需要 ~102px**。原来给 64px 装不下。
    """
    src = _fx("pages/crawler/index.tsx")
    assert "create_time: 92" in src or "create_time: 102" in src, (
        "发布时间列宽仍不足（约需 102px：70px 文本 + 32px padding）"
    )
    # 且要不换行
    i = src.find("'create_time'")
    assert i != -1
    seg = src[i:i + 600]
    assert "nowrap" in seg, "发布时间列缺 whiteSpace: nowrap（会竖排单字）"


def test_notes_table_has_scroll():
    """作品结果表要有横向滚动（之前只给 userColumns 加了，noteColumns 漏了）。

    ⚠️ 注释里**引用了** `scroll={{ x: 520 }}` 的说明文字，
    简单 substring 可能匹配到注释 —— 所以这里用 tokenize 过滤后判断，
    并用 JSX 属性位置（`dataSource` 之后）缩小窗口。
    """
    src = _fx("pages/platform-users/index.tsx")
    i = src.find("dataSource={notes}")
    assert i != -1, "找不到作品结果表"
    # scroll 必须在 dataSource 之后（同一个 <Table> 的属性）
    seg = src[i:i + 400]
    assert "scroll={{ x:" in seg, (
        "作品结果表缺 scroll={{ x }}（窄容器会压扁列）"
    )


def test_notes_title_column_ellipsis():
    """作品标题列要 `ellipsis`（原来既没 width 也没 ellipsis）。"""
    src = _fx("pages/platform-users/index.tsx")
    i = src.find("const noteColumns")
    assert i != -1
    seg = src[i:i + 900]
    assert "ellipsis: true" in seg, "作品标题列缺 ellipsis"


# =============================================================================
# SUPPORTED 的每个键都要能建客户端
# =============================================================================

def test_all_supported_keys_can_create_client():
    """**核心防线**：`SUPPORTED` 里的每个键都必须能 `create_client`。

    ⚠️ 审计怀疑 `bilibili`（别名）建不了客户端（只注册了 `bili`）。
    实测**已正确处理**（`_CLIENT_ALIAS` 从 meta 生成了映射）——
    所以那条是误报。这个测试防的是**将来**又加别名时忘了映射。
    """
    from app.api.v1.users import SUPPORTED, _CLIENT_ALIAS
    from app.services.platforms import create_client

    bad = []
    for plat in SUPPORTED.keys():
        alias = _CLIENT_ALIAS.get(plat, plat)
        try:
            create_client(alias, mode="api", cookie="")
        except Exception as exc:
            bad.append(f"{plat} -> create_client({alias!r}): {type(exc).__name__}")
    assert not bad, "这些平台名建不了客户端：\n  " + "\n  ".join(bad)


# =============================================================================
# 误报的记录（防重复劳动）
# =============================================================================

def test_x_get_replies_filter_is_correct():
    """X 的 `get_replies` 按 `in_reply_to_status_id_str` 筛父评论 —— **是对的**。

    ⚠️ 审计怀疑"X 侧按 handle 筛，会取不到"—— **核实为误报**：
    评论的 `id` 就是 `rest_id`，而 `in_reply_to_status_id_str`
    正是父评论的 `rest_id`，两者一致。

    这个测试留着：将来若有人改成"按 handle 筛"，这里会失败。
    """
    from app.services.platforms.twitter import search_http

    src = inspect.getsource(search_http.get_replies_via_http)
    assert "in_reply_to_status_id_str" in src, (
        "X 的子回复筛选应该用 in_reply_to_status_id_str（= 父评论的 rest_id）"
    )
    assert "parent_comment_id" in src, "应支持按父评论 id 过滤"
