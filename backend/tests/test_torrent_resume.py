"""种子下载断点续传的回归测试（2026-10-01）。

## 背景：种子和 HTTP 下载的"断点续传"不是一回事

    HTTP 下载：断了真的丢，要靠 `Range` 请求续
    种子下载：**BT 协议本身就有分片校验** —— 重新 add 同一种子，
              libtorrent 会扫描已有文件、校验分片、只下缺的部分

所以种子这边**不缺"续传能力"，缺的是"记住有哪些种子"** ——
进程重启后不知道该重新添加哪些。

## 本轮做的两件事

1. **启动恢复**：读数据库里未完成的记录 → 重新 add
   （原来信息**本来就存了** `source_uri`/`save_path`/`hash`，
   但**没有任何代码在启动时读回来**）
2. **resume data 落盘**：让重启后**跳过重新校验**
   （几十 GB 的种子校验要很久）

## ⚠️ 本文件守的坑（都是实测踩到的）

  1. `getattr(rd, key, None) or rd.get(key)` —— libtorrent 对象**没有 `.get`**
  2. `setattr(params, "resume_data", bytes)` —— **C++ 签名不匹配**
  3. 模块**没有 `logger`** 却在异常路径用了它（NameError，平时测不出）
  4. `pause`/`close` 不保存 resume data → 进度白丢
  5. `close()` 不能销毁 session（那会让后续请求拿不到 handle）
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ENGINE = BACKEND / "app" / "services" / "torrent" / "libtorrent_engine.py"
SERVICE = BACKEND / "app" / "services" / "torrent" / "service.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 启动恢复
# =============================================================================

def test_service_has_restore_method():
    """**核心**：`TorrentService` 要有启动恢复方法。"""
    from app.services.torrent.service import TorrentService

    assert hasattr(TorrentService, "restore_active_downloads"), (
        "缺少启动恢复 —— 重启后未完成的种子会全部消失"
    )


def test_restore_skips_terminal_states():
    """**关键**：已完成/已删除的种子**不该**被恢复。

    ⚠️ 恢复它们没有意义，还会：
      · 白白占用"最大活动数"配额
      · 让用户看到"已完成的任务又开始下了"
    """
    from app.services.torrent.service import TorrentService

    assert hasattr(TorrentService, "_TERMINAL_STATES")
    terminal = TorrentService._TERMINAL_STATES
    for s in ("completed", "finished", "seeding", "deleted"):
        assert s in terminal, f"{s} 应被视为终态"


def test_restore_uses_source_uri():
    """恢复要用数据库里的 `source_uri` 重新 add。"""
    from app.services.torrent.service import TorrentService

    src = inspect.getsource(TorrentService.restore_active_downloads)
    assert "source_uri" in src
    assert "add_magnet" in src, "magnet 类型要重新 add_magnet"
    assert "add_torrent_file" in src, "种子文件类型要重新 add_torrent_file"


def test_restore_is_best_effort():
    """**关键**：单个种子恢复失败**不能影响其它**，也不能拖垮启动。

    所以每个失败都要记账（`failed` 列表），而不是抛异常中断。
    """
    from app.services.torrent.service import TorrentService

    src = inspect.getsource(TorrentService.restore_active_downloads)
    assert "failed" in src, "失败要记账"
    assert "continue" in src, "单个失败要 continue（不中断整体）"


def test_restore_runs_at_startup():
    """**关键回归**：`main.py` 启动时要**真的调用**恢复。

    ⚠️ 本仓库反复踩的坑：写好了方法但**没人调**
    （后端实现了前端没接、守卫只加在一个入口…）。
    """
    main_src = (BACKEND / "app" / "main.py").read_text(encoding="utf-8", errors="ignore")
    assert "restore_active_downloads" in main_src, (
        "启动流程里没有调用种子恢复 —— 等于没做"
    )
    # 失败不能拖垮启动
    assert "Torrent resume-on-startup failed" in main_src


# =============================================================================
# resume data
# =============================================================================

def test_engine_has_resume_data_helpers():
    """引擎要有 resume data 的存/取/路径方法。"""
    from app.services.torrent.libtorrent_engine import LibtorrentEngine

    for name in ("_resume_data_path", "_load_resume_data_into",
                 "_save_resume_data", "_drain_alerts"):
        assert hasattr(LibtorrentEngine, name), f"缺少 {name}"


def test_resume_data_in_hidden_subdir():
    """resume data 放 `_resume_data/` 子目录（与 `_metadata_cache` 同级）。"""
    src = _src(ENGINE)
    assert '"_resume_data"' in src
    assert "_metadata_cache" in src, "应与 metadata cache 放同级"


def _code_only(src: str) -> str:
    """从**完整源码**里剥掉注释与 docstring，只留可执行代码。

    ⚠️ 必须传**整个文件**：tokenize 需要合法的缩进结构，
    只传一个函数的片段会抛 `IndentationError`（实测踩到），
    那样 fallback 会把含 docstring 的原文返回，断言就误判了。
    """
    import io
    import tokenize

    out: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING:
            if tok.line.strip().startswith(('"""', "'''", '"', "'")):
                continue
        out.append(tok.string)
    return " ".join(out)


def _function_code(src: str, marker: str, span: int = 5000) -> str:
    """取某段**代码**（先整文件 tokenize，再在结果里找 marker）。

    ⚠️ 两个坑：
      · 不能"先切片再 tokenize" —— 片段缩进不完整会抛 `IndentationError`
      · tokenize 拼接后标识符之间**带空格**（`def _foo` → `def _foo`，
        但 `self._foo` → `self . _foo`），所以 marker 要用
        **不带点号/前缀**的纯名字，找到后往前扩展到函数起点。
    """
    code = _code_only(src)
    i = code.find(marker)
    assert i != -1, f"找不到 {marker}"
    # 往前扩到 "def " 开头，保证包含整个函数（含 def 行）
    start = code.rfind("def ", 0, i)
    if start == -1:
        start = i
    return code[start:start + span]


def test_load_does_not_use_dict_get():
    """**关键回归**：加载 resume data **不能**用 `rd.get(key)`。

    ## 踩坑经过

    `read_resume_data()` 返回的是 `libtorrent.add_torrent_params`
    **对象**（不是 dict），**没有 `.get` 方法**。

    原来写的：

        val = getattr(rd, key, None) or rd.get(key)

    当 `getattr` 返回 `None` 时（magnet 还没元数据，`ti` 就是 None），
    会去调 `rd.get(key)` → **AttributeError** → 被 except 吞掉
    → 整个加载返回 False。

    **症状**：resume 文件明明写出来了（982 字节），
    加载却**永远 False** —— 等于白存，且不报错，极难发现。
    """
    code = _function_code(_src(ENGINE), "_load_resume_data_into")
    assert "rd.get(" not in code and "rd . get (" not in code, (
        "用了 rd.get() —— libtorrent 的 add_torrent_params 没有这个方法"
    )


def test_load_does_not_setattr_resume_data_bytes():
    """**关键回归**：不能 `setattr(params, "resume_data", bytes)`。

    ## 踩坑经过

    实测报 **C++ 签名不匹配**：

        None.None(add_torrent_params, bytes)
        did not match C++ signature: ...

    libtorrent 2.0 的 `resume_data` 不是裸 bytes 字段。
    正确做法：`read_resume_data()` 返回的就是一个
    `add_torrent_params` —— 直接逐字段搬到我们的 params 上。
    """
    code = _function_code(_src(ENGINE), "_load_resume_data_into")
    # ⚠️ 排除 `_resume_data`（那是路径辅助函数名，合法）
    stripped = code.replace("_resume_data", "")
    assert "resume_data" not in stripped, (
        "还在往 params 塞 resume_data bytes —— libtorrent 会报 C++ 签名不匹配"
    )


def test_engine_has_logger_defined():
    """**回归**：模块必须定义 `logger`（否则异常路径 NameError）。

    ⚠️ 实测踩到：本模块原来**没有 logger**，我加 resume data 时
    直接写了 `logger.debug(...)` —— 只在异常路径触发，
    平时测不出来，一旦真的读失败就炸。
    """
    src = _src(ENGINE)
    assert "logger = logging.getLogger" in src, "没有定义 logger"
    assert "import logging" in src


def test_pause_saves_resume_data():
    """**关键**：`pause` 时要请求保存 resume data。

    ⚠️ 不保存的话，暂停/重启后下次要**重新校验全部已下载数据** ——
    几十 GB 的种子会卡很久。
    """
    from app.services.torrent.libtorrent_engine import LibtorrentEngine

    src = inspect.getsource(LibtorrentEngine.pause)
    assert "_save_resume_data" in src, "pause 没保存 resume data"


def test_close_saves_resume_data():
    """**关键**：`close()` 要保存所有 resume data。

    ⚠️ 原来是直接 `return None` —— 进程退出时**所有种子的校验进度都丢了**。
    """
    from app.services.torrent.libtorrent_engine import LibtorrentEngine

    src = inspect.getsource(LibtorrentEngine.close)
    assert "save_resume_data" in src, "close 没保存"
    assert "_drain_alerts" in src, "保存是异步的，要处理 alert 才能写盘"
    assert "asyncio.sleep" in src, "要等 libtorrent 生成完"


def test_close_does_not_destroy_session():
    """**关键**：`close()` **不能**销毁 session。

    ⚠️ `_session` 是**类变量（单例）**，每个 HTTP 请求都会新建
    `TorrentService` 并在结束时 `close()`。如果 close 把 session
    销毁了，**下一个请求就拿不到 handle**（种子全部"消失"）。

    所以 close 只做"保存状态"，不 `reset()`/`None`。
    """
    from app.services.torrent.libtorrent_engine import LibtorrentEngine

    src = inspect.getsource(LibtorrentEngine.close)
    code = "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("#")
    )
    assert "LibtorrentEngine._session = None" not in code, "close 销毁了 session"
    assert "self._session = None" not in code, "close 销毁了 session"
    assert "_handles.clear()" not in code, "close 清空了 handles"


def test_alerts_drained_on_poll():
    """`list_torrents` 要处理 alert（前端轮询当心跳用）。

    ⚠️ libtorrent 的 `save_resume_data()` 是**异步**的：
    要处理 `save_resume_data_alert` 才能把数据写文件。
    不处理的话 resume data **永远写不出去**。
    """
    from app.services.torrent.libtorrent_engine import LibtorrentEngine

    src = inspect.getsource(LibtorrentEngine.list_torrents)
    assert "_drain_alerts" in src


def test_resume_data_survives_bad_input():
    """**健壮性**：损坏/不存在的 resume 文件不能让加载崩。

    ⚠️ resume data 只是**优化** —— 没有它 libtorrent 会退回
    "重新校验"，功能仍然正常。所以读失败必须静默降级（返回 False），
    **不能抛异常**中断种子添加。
    """
    from app.services.torrent.libtorrent_engine import LibtorrentEngine

    src = inspect.getsource(LibtorrentEngine._load_resume_data_into)
    assert "except Exception" in src, "要吞异常（降级而非中断）"
    assert "return False" in src
    # 不能抛出去
    assert "raise" not in src.split("except Exception")[-1][:200], (
        "异常路径不该 raise（会让种子添加失败）"
    )
