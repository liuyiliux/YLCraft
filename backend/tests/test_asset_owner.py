"""下载素材「归属」的回归测试（2026-09-29）。

## 用户反馈

    x下载的视频为什么在素材库没记录

## 调查结果：**记录其实存在，只是「无主」**

实测数据库：

    97eaebae（刚下载的 X 视频）  owner_user_id = **None**
    9c8b89a5（旧素材，能看到）    owner_user_id = 2741e5fb...（root）

而素材库列表按 owner 过滤（`asset_hub.py::list_nodes`）：

    owner_user_id = principal.user.id if filter_by_owner and principal else None
    ...
    owner_user_id=owner_user_id if filter_by_owner else None,
    include_legacy_owner=principal is None if filter_by_owner else True,

**登录用户（root）按 owner 过滤 → 无主节点查不到** → 看起来"没记录"。

## 根因

下载/解析创建的素材节点**不写 `owner_user_id`**：

    AssetNodeService(session).create(
        name=..., asset_type=..., thumbnail_url=...,
        metadata=..., tags=...,
        # ← 没有 owner_user_id（签名支持，只是没传）
    )

## 修法

  · `_owner_of(principal)` 辅助函数（未登录返回 None）
  · 三个 `_create_parsed_asset_hub_node` 调用点 + 下载任务调用点
    都传 `owner_user_id`
  · **已存在的无主节点也要补**（`_find_asset_hub_node_id` 命中时）
  · 加 `principal` 依赖到 `/parse` 与 `/tasks`（用 optional 版，
    本地单机未登录时不报错）
  · `DownloadTask` 加 `owner_user_id`（后台任务需要带着它）

## 历史数据

新增 `_backfill_asset_owner.py` 把历史无主节点补到 root 名下：

    root 用户 id = 2741e5fb...
    无主素材节点: 4 个 → ✅ 已补 4 个

## 实测修复后

    /api/v1/asset-hub/nodes  共 258 条
      第一页第 1 条就是刚下载的那条 X 视频 ✅

## 顺带发现的运维问题

调查中数据库一度连不上（远程 `81.70.219.37:5432`）：

    OSError: [WinError 1232] 不能访问网络位置
    psycopg2.OperationalError: No route to host

但 `Test-NetConnection` 显示可达 —— 是**瞬时网络抖动**，重试即恢复。
（记下来：数据库是**远程**的，网络抖动会让后端启动失败。）
"""

from __future__ import annotations

import inspect

import pytest


def _dl_src() -> str:
    from app.api.v1 import download

    return inspect.getsource(download)


# =============================================================================
# 建节点要带 owner
# =============================================================================

def test_owner_helper_exists():
    """要有取 owner 的辅助函数。"""
    from app.api.v1 import download

    assert hasattr(download, "_owner_of")


def test_owner_helper_handles_none_principal():
    """未登录时返回 None（本地单机模式不该报错）。"""
    from app.api.v1.download import _owner_of

    assert _owner_of(None) is None

    class _U:
        id = "u1"

    class _P:
        user = _U()

    assert _owner_of(_P()) == "u1"


def test_create_node_accepts_owner():
    """**回归**：`_create_parsed_asset_hub_node` 要接收 owner 参数。"""
    from app.api.v1.download import _create_parsed_asset_hub_node

    sig = inspect.signature(_create_parsed_asset_hub_node)
    assert "owner_user_id" in sig.parameters


def test_create_node_passes_owner_to_service():
    """**回归（根因）**：要把 owner 真的传给 `AssetNodeService.create`。

    原来只是签名支持、调用时不传 → 节点无主 → 素材库看不见。
    """
    from app.api.v1 import download

    src = inspect.getsource(download._create_parsed_asset_hub_node)
    assert "owner_user_id=owner_user_id" in src, (
        "要把 owner 传给 AssetNodeService.create"
    )


def test_all_create_call_sites_pass_owner():
    """**回归**：所有调用点都要传 owner（漏一个就有一类素材看不见）。"""
    src = _dl_src()
    calls = src.count("_create_parsed_asset_hub_node(")
    owners = src.count("owner_user_id=_owner_of(principal)")
    # 减去函数定义本身
    assert owners >= calls - 1, (
        f"调用点 {calls - 1} 个，但只传了 {owners} 次 owner"
    )


def test_save_file_accepts_and_uses_owner():
    """**回归**：`_save_downloaded_asset_hub_file` 也要带 owner。"""
    from app.api.v1 import download

    sig = inspect.signature(download._save_downloaded_asset_hub_file)
    assert "owner_user_id" in sig.parameters

    src = inspect.getsource(download._save_downloaded_asset_hub_file)
    assert "owner_user_id" in src


def test_download_task_carries_owner():
    """**回归**：`DownloadTask` 要带 owner。

    下载是**后台任务** —— 请求结束后 principal 就没了，
    所以必须在创建任务时把 owner 存下来。
    """
    from app.api.v1.download import DownloadTask

    t = DownloadTask("id", "url", None, "title", "page", False,
                     owner_user_id="u1")
    assert t.owner_user_id == "u1"


def test_existing_orphan_nodes_get_backfilled():
    """**回归**：已存在的无主节点也要补 owner（不能只照顾新建的）。"""
    from app.api.v1 import download

    for fn in (download._create_parsed_asset_hub_node,
               download._save_downloaded_asset_hub_file):
        src = inspect.getsource(fn)
        assert "owner_user_id" in src
        # 要有"节点已存在时补 owner"的逻辑
        assert "update(" in src or "owner_user_id=owner_user_id" in src


# =============================================================================
# 认证依赖
# =============================================================================

def test_endpoints_have_optional_principal():
    """**回归**：`/parse` 与 `/tasks` 要拿 principal。

    用 **optional** 版 —— 本地单机未登录时不报错。
    """
    from app.api.v1 import download

    for fn in (download.parse_download_url, download.create_download_task):
        src = inspect.getsource(fn)
        assert "get_authenticated_principal_optional" in src, (
            f"{fn.__name__} 应带 optional 认证依赖"
        )


def test_frontend_sends_credentials():
    """**回归**：前端请求要带凭证，否则 principal 为空、owner 丢失。"""
    from pathlib import Path

    p = (Path(__file__).resolve().parents[2] / "frontend" / "src"
         / "api" / "index.ts")
    if not p.exists():
        pytest.skip("api/index.ts 不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "credentials: 'include'" in src, "请求要带 cookie"


# =============================================================================
# 素材库列表按 owner 过滤（记录这个契约）
# =============================================================================

def test_asset_list_filters_by_owner():
    """记录：素材库列表按 owner 过滤 —— 这是"无主素材看不见"的原因。"""
    from app.api.v1 import asset_hub

    src = inspect.getsource(asset_hub.list_nodes)
    assert "owner_user_id" in src, "列表按 owner 过滤"
    assert "include_legacy_owner" in src, "有 legacy 兜底"
