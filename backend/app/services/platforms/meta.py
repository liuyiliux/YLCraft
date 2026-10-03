"""YLCraft — 平台元数据的**单一事实来源**（2026-10-01 加）。

## ⚠️ 这个模块解决什么问题

### 改造前：平台元数据散落 4 个文件，共 58 项内联映射

    api/v1/users.py            SUPPORTED (含 conn_platform/cookie_domain/no_login)
                               _CLIENT_ALIAS (5 项)
    api/v1/comments.py         COMMENTS_SUPPORTED
                               (连接名, cookie域名) 内联字典 (3 项)
                               client_name 逐个别名转换
    services/platforms/
      health_routes.py         PROBE_SEARCH_TYPE
                               PROBE_KEYWORD_BY_PLATFORM
                               平台→连接名 内联字典 (19 项)
                               no_login = p in ("youtube","telegram")   ← 硬编码
    api/v1/platform_stats.py   _ALIAS (7 项)

**后果（真实痛点）**：新增一个平台要改 **4~5 个文件**，而且
**漏一个就静默出错**：
  · 漏了 `comments.py` 的映射 → 评论接口 `KeyError`
  · 漏了 `health_routes.py` 的探测类型 → 体检拿不到结果
  · 别名忘了加 → `create_client` 找不到客户端

**这正是"公共代码成了平台知识的垃圾场"** ——
公共文件不该记住每个平台的特征。

### 改造后：每个平台在自己文件夹声明，公共文件从它生成

    platforms/<平台>/meta.py  ← 只改这里
    platforms/meta.py         ← 本模块：聚合 + 查询 API
    api/v1/users.py 等 4 个文件 ← 从 meta 生成，**不再硬编码**

## 用法

```python
from app.services.platforms.meta import (
    get_meta,           # 按名/别名取元数据（找不到返回 None）
    resolve_name,       # 别名 → 正式名（"wb" → "weibo"）
    all_metas,          # 所有已声明元数据的平台
    supports,           # 能力查询："comments" in supports("weibo")
    no_login_platforms, # 免登录平台集合
)
```

## ⚠️ 设计原则

1. **平台自己声明**（`<平台>/meta.py`），公共层只聚合
2. **别名不影响正式名**：`resolve_name("wb") == "weibo"`
3. **能力用声明而非猜测**：`capabilities={"comments": True}`
   —— 而不是让公共代码去 `hasattr` 或猜名字
4. **找不到就返回 None**，由调用方决定报错方式
   （不在这里抛异常 —— 有的调用方要报 501，有的要报 400）
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set

logger = logging.getLogger("ylcraft.platforms.meta")

_PLATFORMS_DIR = Path(__file__).resolve().parent


# =============================================================================
# 翻页模型
# =============================================================================

#: 支持翻页 —— 前端用页码分页器
PAGED = "paged"
#: 固定只返回一页 —— 前端用「加载更多」往下追加
SINGLE = "single"

PAGINATION_MODELS = frozenset({PAGED, SINGLE})


@dataclass(frozen=True)
class PlatformMeta:
    """一个平台的元数据（**由平台自己声明**）。"""

    # 正式名（客户端注册名，如 "weibo"）
    name: str
    # 别名（前端/连接表里可能出现的写法，如 ["wb"]）
    aliases: FrozenSet[str] = frozenset()
    # 连接表 `platform_connections.platform` 里的值（大写，如 "WEIBO"）
    conn_platform: str = ""
    # `netscape_to_header(raw, domain)` 用的域名
    #
    # ⚠️ 必须写对 —— 实测认的是这些名字，写错会返回 0 字符 cookie：
    #     微博 → "weibo"（**不是** weibo.com；主站 cookie 在 m.weibo.cn 无效）
    #     X    → "x.com"（**不是** twitter）
    #     B站  → "bili" （**不是** bilibili）
    cookie_domain: str = ""
    # 免登录平台：不需要凭证也能取公开数据
    no_login: bool = False
    # 体检探针用的搜索类型（"" = 该平台没有内容搜索，跳过探针）
    probe_search_type: str = ""
    # 体检探针用的关键词（留空则用默认的"美食"）
    probe_keyword: str = ""
    # 能力声明（接口层据此判断，**不靠 hasattr 猜**）
    capabilities: FrozenSet[str] = frozenset()
    # 该平台在「博主中心」是否可用（前端配置参考）
    user_dimension: bool = True
    # 该平台搜索的**翻页模型**（前端据此选分页器 / 加载更多）
    #
    # ⚠️ 不是所有平台都支持翻页（2026-10-03 实测）——
    # 用同一个分页器套所有平台，会让"翻不过去"的平台
    # 出现"显示只有 1 页 / 点下一页报错 / 重复数据"。
    #
    #     PAGED     支持翻页 → 前端用页码分页器
    #     SINGLE    固定只返回一页 → 前端用「加载更多」往下追加
    #
    # 每页 20 条、连续翻 4 页的实测（2026-10-03，关键词「沈阳」）：
    #
    #     平台      p1  p2  p3  p4  累计唯一  结论
    #     bili      20  20  20  20   77      PAGED（total=1000 真实总数）
    #     weibo     20  17  20  20   52      PAGED
    #     kuaishou  20  20  20  20   65      PAGED
    #     twitter   20  20  20  20   77      PAGED
    #     youtube   20  20  20  20   74      PAGED
    #     douyin     0   0   0   0    0      SINGLE（offset>0 服务端返空）
    #
    # ⚠️ 平台行为会变（抖音 09-27 还能翻页、09-28 就不行了），
    #    所以下面每条都标了实测日期，改之前先复验。
    pagination: str = PAGED
    # 单页型平台**一次最多给多少条**（用于前端显示"单次上限"提示）。
    # 抖音实测 17~18 条（count 上限 20，抖音自己少给 2 条）。
    single_page_max: int = 0

    @property
    def all_names(self) -> Set[str]:
        """正式名 + 所有别名。"""
        return {self.name, *self.aliases}


# 平台元数据注册表（懒加载，由 `_discover()` 填充）
_REGISTRY: Dict[str, PlatformMeta] = {}
_DISCOVERED = False


def _discover() -> None:
    """扫描 `platforms/<平台>/meta.py`，聚合元数据。

    ⚠️ 用**约定的文件位置**（`<平台>/meta.py` 里的 `PLATFORM_META`）
    而不是自动推断 —— 显式声明比魔法更可靠，
    且新增平台时"有没有声明元数据"一眼可见。
    """
    global _DISCOVERED
    if _DISCOVERED:
        return

    for entry in sorted(_PLATFORMS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("__"):
            continue
        meta_file = entry / "meta.py"
        if not meta_file.exists():
            continue
        try:
            mod = importlib.import_module(
                f"app.services.platforms.{entry.name}.meta"
            )
        except Exception as exc:
            logger.warning(
                "[meta] 加载 %s/meta.py 失败：%s: %s",
                entry.name, type(exc).__name__, exc,
            )
            continue

        raw = getattr(mod, "PLATFORM_META", None)
        if not isinstance(raw, dict):
            logger.warning("[meta] %s/meta.py 没有 PLATFORM_META 字典", entry.name)
            continue

        try:
            meta = PlatformMeta(
                name=raw["name"],
                aliases=frozenset(raw.get("aliases") or []),
                conn_platform=raw.get("conn_platform") or raw["name"].upper(),
                cookie_domain=raw.get("cookie_domain") or raw["name"],
                no_login=bool(raw.get("no_login")),
                probe_search_type=raw.get("probe_search_type") or "",
                probe_keyword=raw.get("probe_keyword") or "",
                capabilities=frozenset(raw.get("capabilities") or []),
                user_dimension=bool(raw.get("user_dimension", True)),
                pagination=raw.get("pagination") or PAGED,
                single_page_max=int(raw.get("single_page_max") or 0),
            )
        except KeyError as exc:
            logger.warning("[meta] %s/meta.py 缺字段 %s", entry.name, exc)
            continue

        for n in meta.all_names:
            if n in _REGISTRY and _REGISTRY[n].name != meta.name:
                logger.warning(
                    "[meta] 别名冲突：%r 同时被 %s 和 %s 声明",
                    n, _REGISTRY[n].name, meta.name,
                )
            _REGISTRY[n] = meta

    _DISCOVERED = True
    logger.info("[meta] 已加载 %d 个平台的元数据", len(all_metas()))


def get_meta(platform: str) -> Optional[PlatformMeta]:
    """按名或别名取元数据（找不到返回 None）。"""
    _discover()
    return _REGISTRY.get((platform or "").strip().lower())


def resolve_name(platform: str) -> str:
    """别名 → 正式名（`"wb"` → `"weibo"`）。

    ⚠️ 未知平台**原样返回**（不抛错）——
    由调用方决定怎么报（有的要 501，有的要 400）。
    """
    meta = get_meta(platform)
    return meta.name if meta else (platform or "").strip().lower()


def all_metas() -> List[PlatformMeta]:
    """所有已声明元数据的平台（按正式名去重）。"""
    _discover()
    seen: Dict[str, PlatformMeta] = {}
    for m in _REGISTRY.values():
        seen[m.name] = m
    return sorted(seen.values(), key=lambda x: x.name)


def known_names() -> Set[str]:
    """所有已知的平台名（含别名）。"""
    _discover()
    return set(_REGISTRY)


def supports(platform: str, capability: str) -> bool:
    """该平台是否声明了某个能力。

        supports("weibo", "comments")   → True
        supports("weibo", "replies")    → False（微博楼中楼拿不到）

    ⚠️ 能力是**声明**的，不是猜的 —— 所以平台必须在自己 meta.py 里
    如实写清（写 True 但没实现，接口层会调用失败）。
    """
    meta = get_meta(platform)
    return bool(meta and capability in meta.capabilities)


def supports_any(capability: str) -> Set[str]:
    """哪些平台声明了某能力（返回正式名集合）。"""
    return {m.name for m in all_metas() if capability in m.capabilities}


def no_login_platforms() -> Set[str]:
    """免登录平台（正式名集合）。"""
    return {m.name for m in all_metas() if m.no_login}


def supports_pagination(platform: str) -> bool:
    """该平台是否**支持翻页**（True → 分页器；False → 「加载更多」）。

        supports_pagination("bili")     → True
        supports_pagination("douyin")   → False（单次上限 18 条）

    未知平台按**保守**处理（返回 True）：大多数平台都支持翻页，
    猜错的后果只是"多一个分页器"，而反过来猜会让能用分页的平台
    退化成"一直点加载更多"。
    """
    meta = get_meta(platform)
    if not meta:
        return True
    return meta.pagination != SINGLE


def single_page_platforms() -> Set[str]:
    """固定只返回一页的平台（正式名集合）。

    这些平台前端**必须**用「加载更多」而不是页码分页器：
    抖音实测 offset>0 返回空数据，点"第 2 页"必然失败。
    """
    return {m.name for m in all_metas() if m.pagination == SINGLE}


def pagination_info(platform: str) -> Dict[str, Any]:
    """给 API 层/前端用的翻页信息。

    ```json
    {"model": "paged", "single_page_max": 0}
    {"model": "single", "single_page_max": 18}
    ```
    """
    meta = get_meta(platform)
    if not meta:
        return {"model": PAGED, "single_page_max": 0}
    return {"model": meta.pagination, "single_page_max": meta.single_page_max}


def probe_config() -> Dict[str, Dict[str, str]]:
    """体检探针配置：`{平台名: {"search_type": ..., "keyword": ...}}`。

    替代 `health_routes.py` 里那两个内联字典。
    """
    return {
        m.name: {"search_type": m.probe_search_type, "keyword": m.probe_keyword}
        for m in all_metas()
    }
