"""图文导入素材库的可见性契约测试。

## 用户问："素材库支持查看这种帖子吗"

走完发现**两个真问题**（2026-09-27）：

### 1. 导入的记录 owner=NULL → 素材库界面上看不到

素材库列表按 `owner_user_id` 过滤（`assets.py::list_assets`）。
`crawler/import` 原来**完全不带认证**，导入的记录 owner 为 NULL ——
普通登录用户看不到，表现为"导入返回成功但素材库一直是空的"。

现已：`crawler/import` 加 `get_authenticated_principal_optional` 依赖，
owner 逐层传到 `AssetNodeService.create(owner_user_id=...)`。

### 2. 去重命中旧记录 → 集合结构根本没建

用户在「去水印解析」页解析时，parse 会先建一条该 `source_url` 的
**单节点**记录。之后点「导入素材库」，去重直接命中它并 continue ——
于是集合没建、图集里的图一张都进不来。

现已：命中旧记录时若其实是多图图文，就地**升级**为集合并补建子图
（保留原 id，避免画布引用/发布记录失效）。

## 排查中踩的坑（记录下来避免重复）

  × 用 `limit` 当分页参数 —— 前端用的是 **page_size**，导致误判"列表为空"
  × 无认证请求 assets 列表 —— owner 过滤后必然为空，也像"功能坏了"
  × `CAST(:imgs AS jsonb)` + `text(":name")` → PG 推断不出类型（IndeterminateDatatypeError）
  × `AsyncSession` 没有 `exec_driver_sql`（那是同步 Session 的）
  × `id` 列是 UUID，bindparam 标成 TEXT 会报 `uuid = character varying`
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# owner 归属
# =============================================================================

def test_import_endpoint_requires_principal():
    """导入端点必须取登录用户，否则 owner=NULL、界面看不到。"""
    from app.api.v1 import crawler as crawler_api

    src = inspect.getsource(crawler_api.import_to_assets)
    assert "get_authenticated_principal_optional" in src, "应注入认证依赖"
    assert "principal_owner_user_id" in src, "应换算 owner id"


def test_import_service_accepts_owner():
    """service 层要接收并透传 owner_user_id。"""
    from app.services.crawler import service as svc

    sig = inspect.signature(svc.CrawlerService.import_to_asset_library)
    assert "owner_user_id" in sig.parameters

    src = inspect.getsource(svc.CrawlerService.import_to_asset_library)
    assert "owner_user_id=owner_user_id" in src, "创建节点时必须带上 owner"


def test_collection_creation_sets_owner():
    """建集合容器与子图都要带 owner。"""
    from app.services.crawler import service as svc

    src = inspect.getsource(svc.CrawlerService._import_image_collection)
    # 容器 + 子图各一处
    assert src.count("owner_user_id=owner_user_id") >= 2


def test_upgrade_also_backfills_owner():
    """升级旧记录时要补上 owner（旧记录可能是 parse 阶段建的 NULL）。"""
    from app.services.crawler import service as svc

    src = inspect.getsource(svc.CrawlerService._upgrade_to_collection)
    assert "owner_user_id" in src
    assert "owner_user_id IS NULL" in src, "只补 NULL，不覆盖已有归属"


# =============================================================================
# 去重命中时升级为集合
# =============================================================================

def test_dedup_hit_upgrades_to_collection():
    """**回归**：去重命中旧记录时，多图图文要升级成集合。

    否则用户"解析过再导入"就永远看不到图集（集合结构被跳过）。
    """
    from app.services.crawler import service as svc

    src = inspect.getsource(svc.CrawlerService.import_to_asset_library)
    assert "_upgrade_to_collection" in src
    # 升级必须发生在 continue 之前（即在 existing 分支内）
    i_existing = src.find("if existing_id:")
    i_upgrade = src.find("_upgrade_to_collection")
    assert i_existing != -1 and i_upgrade != -1
    assert i_existing < i_upgrade, "升级逻辑应在去重命中分支里"


def test_upgrade_keeps_original_id():
    """升级要保留原 id（画布引用、发布记录不会失效）。"""
    from app.services.crawler import service as svc

    src = inspect.getsource(svc.CrawlerService._upgrade_to_collection)
    assert "return existing_node_id" in src, "应返回原 id 而不是新建"


def test_upgrade_skips_existing_children():
    """补图时要跳过已存在的子节点，避免重复。"""
    from app.services.crawler import service as svc

    src = inspect.getsource(svc.CrawlerService._upgrade_to_collection)
    assert "remote_url" in src, "应按 remote_url 判断子节点是否已存在"
    assert "if url in have" in src


def test_upgrade_failure_falls_back():
    """升级失败要回退到旧行为，不能让整个导入挂掉。"""
    from app.services.crawler import service as svc

    src = inspect.getsource(svc.CrawlerService._upgrade_to_collection)
    assert "return None" in src, "失败应返回 None 让调用方回退"
    assert "rollback" in src, "失败应回滚事务"


# =============================================================================
# SQL 参数类型（踩过的坑）
# =============================================================================

def test_upgrade_binds_explicit_types():
    """**回归**：JSONB 参数必须显式标注类型。

    `CAST(:imgs AS jsonb)` 用 `text(":name")` 占位时 PG 推断不出类型，
    报 `IndeterminateDatatypeError`。
    `id` 是 UUID 列，标成 TEXT 会报 `uuid = character varying`。

    只检查**真实代码**，不检查注释——注释里专门记录了这几个坑
    （含 `exec_driver_sql` 字样），对全文断言会被注释误伤。
    """
    from app.services.crawler import service as svc

    src = inspect.getsource(svc.CrawlerService._upgrade_to_collection)
    code = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )
    assert "bindparam" in code, "应显式声明参数类型"
    assert "types.Text" in code
    assert "PG_UUID" in code or "UUID" in code, "id 必须标成 UUID"
    assert "db_session.exec_driver_sql" not in code, (
        "AsyncSession 没有 exec_driver_sql（那是同步 Session 的方法）"
    )


# =============================================================================
# 前端契约
# =============================================================================

def test_frontend_supports_collection_type():
    """前端素材库要认识 collection 类型（标签 + 筛选）。"""
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "pages" / "assets" / "index.tsx"
    )
    if not page.exists():
        pytest.skip("前端源码不在预期位置")
    src = page.read_text(encoding="utf-8", errors="ignore")
    assert "collection" in src, "应有 collection 类型"
    assert "'集合'" in src or '"集合"' in src, "应有中文标签"


def test_frontend_uses_page_size_param():
    """**回归**：前端分页参数是 page_size（不是 limit）。

    排查时用 limit 请求，列表恒为空，误判成"素材库不支持"。
    """
    from pathlib import Path

    api = (
        Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "api" / "index.ts"
    )
    if not api.exists():
        pytest.skip("前端源码不在预期位置")
    src = api.read_text(encoding="utf-8", errors="ignore")
    i = src.find("export const listAssets")
    assert i != -1
    seg = src[i:i + 600]
    assert "page_size" in seg, "应使用 page_size"
