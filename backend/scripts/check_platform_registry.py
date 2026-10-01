#!/usr/bin/env python
"""
跨平台一致性检查（新增/接入平台时的守门脚本）。

背景：接入番茄时踩过一组连环坑——同一个"平台清单"散落在四处，
改一处漏三处，表现是"业务侧早就支持了，但 UI 上根本没有入口"、
或"点了浏览器模式报暂不支持"。这个脚本把四处清单钉在一起自动对账。

四处清单：
  1. app/db/models/platform_connection.py  PlatformType（Python 枚举）
  2. app/db/database 的 PG 原生枚举 platformtype（只有 Postgres 才有；需迁移同步）
  3. app/api/v1/platforms.py               SUPPORTED_PLATFORMS（前端可用的平台）
  4. app/services/cookies/base.py          PLATFORM_LOGIN_URLS / PLATFORM_DOMAINS /
                                           PLATFORM_TEST_URLS（浏览器获取 Cookie 必需）
  5. app/services/cookies/platforms/__init__.py  _detector_registry（Patchright 检测器）
  6. frontend/src/pages/accounts/index.tsx       PLATFORM_METAS（账号中心 UI 入口）

用法：
    python scripts/check_platform_registry.py            # 检查全部平台
    python scripts/check_platform_registry.py fanqie xhs # 只检查指定平台

退出码：0 = 全部通过；1 = 存在阻断性问题（CI / 提交前应拦截）
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

# Windows 控制台默认是 GBK，直接打印中文会 UnicodeEncodeError。
# 这里强制 stdout/stderr 用 UTF-8，脚本才能在任意机器上稳定输出。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

# 只需 UI 展示、不需要浏览器取 Cookie 的平台（容器所列 allowed_missing）
UI_ONLY_PLATFORMS = {"openai", "anthropic", "minimax", "google", "s3", "ftp", "webdav"}

# 已知历史缺口：这些平台从未实现浏览器取 Cookie / 前端入口，属既有状态。
# 单独列出而非静默忽略——新接入平台不得加入此表。
# 已知历史缺口：这几个平台**从未**支持浏览器取 Cookie
# （没有 detector、账号中心也没入口），用 --allow-known 可临时放行。
#
# ⚠️ 修好一个就从这里删掉 —— 否则校验器会对已修的平台继续放行，
# 缺口会重新溜进来（`twitter` 2026-09-28 修好后已移出）。
#
# ⚠️ `youtube`（2026-10-01）：**采集客户端已实现**（platforms/youtube/，
#    搜索/详情/频道都通了，用户开 VPN 后实测），但它**不需要登录** ——
#    yt-dlp 走公开数据，公开内容无需 Cookie。
#    所以这里的"缺 detector"是**设计如此**，不是待办：
#    没有登录态就没有"浏览器取 Cookie"这回事。
#    保留在 KNOWN_GAPS 是为了让校验器知道这是**已知且有理由**的状态，
#    而不是漏配。若将来要支持"登录后才能看的内容"（会员/年龄限制），
#    再补 detector 并从本表移出。
#
# ⚠️ `telegram`（2026-10-01）：同 youtube —— **公开频道免登录**
#    （`t.me/s`，含频道内 `?q=` 关键词搜索，已实现）。
#    它的凭证走的是 **MTProto 登录**（api_id/api_hash + 手机号验证码），
#    在 `/api/v1/telegram/auth/*` 与 `/telegram-login` 页面，
#    **不走**账号中心的"浏览器抓 cookie"流程 —— 所以这里缺 detector
#    同样是**设计如此**，不是待办。
KNOWN_GAPS = {"telegram", "tiktok", "youtube"}


def load_env() -> None:
    """加载 backend/.env，与 uvicorn 启动行为保持一致。"""
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def extract_platform_types(source: str) -> set[str]:
    """从 platform_connection.py 提取 PlatformType 成员名。"""
    block = re.search(r"class PlatformType\(str, enum\.Enum\):(.*?)(?=\nclass |\Z)", source, re.S)
    if not block:
        return set()
    return set(re.findall(r"^\s{4}([A-Z][A-Z0-9_]*)\s*=", block.group(1), re.M))


def extract_supported_platforms(source: str) -> set[str]:
    """只取 SUPPORTED_PLATFORMS 列表里的 value。

    不能全文件扫 `{"value": ...}` —— 下同文件还有 AUTH_TYPES /
    ACQUISITION_METHODS 两个列表，混进来会得到 cookie / active / unknown
    等"假平台"，把报告污染成一堆噪音。
    """
    block = re.search(r"SUPPORTED_PLATFORMS\s*=\s*\[(.*?)\n\]", source, re.S)
    if not block:
        return set()
    return set(re.findall(r'\{"value":\s*"([^"]+)"', block.group(1)))


def extract_dict_keys(source: str, name: str) -> set[str]:
    block = re.search(rf"{name}\s*=\s*\{{(.*?)\n\}}", source, re.S)
    if not block:
        return set()
    return set(re.findall(r'["\']([a-z0-9_]+)["\']\s*:', block.group(1)))


def extract_registry_keys(source: str, name: str) -> set[str]:
    block = re.search(rf"{name}: dict\[str, str\] = \{{(.*?)\n\}}", source, re.S)
    if not block:
        return set()
    return set(re.findall(r'["\']([a-z0-9_]+)["\']\s*:', block.group(1)))


def extract_frontend_metas(source: str) -> set[str]:
    return set(re.findall(r"value:\s*'([a-z0-9_]+)'", source))


# =============================================================================
# 能力层检查（2026-09-29 加）
# =============================================================================
#
# 上面 1-4 项只保证「登记齐全」。但**登记齐全 ≠ 功能接通** ——
# 本轮实测踩的四个坑都属于后者，而且**都不报错**：
#
#   ① X 的「我的数据」下拉忘了加   → 用户"根本选不到"
#   ② 微博下面显示抖音的创作者数据 → `else` 无条件走抖音
#   ③ X 搜索没有"下一页"           → 后端从没设 `has_more`
#   ④ 下载的素材在库里看不到       → 建节点时漏了 `owner_user_id`
#
# 这些只能"各层对照"才查得出来，所以这里做**跨层一致性**检查。

# 平台名 → 前端各下拉里应该出现的值（含别名）
_FRONTEND_PLATFORM_VALUES = {
    "xhs": ["xiaohongshu"],
    "twitter": ["twitter"],
    "weibo": ["weibo"],
    "douyin": ["douyin"],
    "bilibili": ["bili"],
    "fanqie": ["fanqie"],
}

# 「我的数据」下拉**本该有**的平台。
#
# ⚠️ 只查"应该支持"的，不是所有平台 —— 否则 AI 平台
# （openai/anthropic/minimax）和只有 Cookie 的平台（telegram/wechat_mp；zhihu 已于 2026-10-01 移除）
# 会被误报。
#
# 判定依据：后端实现了 `get_self_profile` 或 `get_user_videos`
# （即真的能查"我的"数据）。
_MY_DATA_PLATFORMS = {
    "douyin", "xhs", "bilibili", "weibo", "twitter",
}

# 有"搜索 + 分页"能力、因而**必须给 has_more** 的平台
_SEARCH_PAGED_PLATFORMS = {
    "xhs", "bilibili", "douyin", "weibo", "twitter", "kuaishou",
}

# 「搜博主 → 看作品」可用的平台（前端「博主中心」下拉要有）
_USER_SEARCH_PLATFORMS = {
    "douyin", "xhs", "bilibili", "kuaishou",
}


def _fe_file(rel: str) -> str:
    p = REPO_ROOT / "frontend" / "src" / rel
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def check_capability_layers(plat: str) -> list[tuple[str, bool, str]]:
    """返回 [(检查项, 是否通过, 未通过时的提示)]。

    检查的是"**后端起效了，但别的层没接上**"这类不报错的坑。
    """
    out: list[tuple[str, bool, str]] = []

    # ---- A. 前端各下拉有没有这个平台 ----
    #
    # 实测：X 的后端（/users/me + /users/videos）全部可用，
    # 但前端下拉漏了 → 用户"根本选不到"。
    # **快手又漏了一次**（2026-09-30）—— 所以这里要查**全部**入口，
    # 不是只查「我的数据」那一处。
    my_data = _fe_file("pages/my-platform-data/index.tsx")
    if my_data and plat in _MY_DATA_PLATFORMS:
        vals = _FRONTEND_PLATFORM_VALUES.get(plat, [plat])
        has = any(f"value: '{v}'" in my_data for v in vals)
        out.append((
            "前端「我的数据」下拉",
            has,
            f"缺 {vals} —— 后端支持但用户选不到（X/快手都这样漏过）",
        ))

    # 博主中心（搜人→看作品）——搜博主能力可用的平台都该有
    users_page = _fe_file("pages/platform-users/index.tsx")
    if users_page and plat in _USER_SEARCH_PLATFORMS:
        vals = _FRONTEND_PLATFORM_VALUES.get(plat, [plat])
        has = any(f"value: '{v}'" in users_page for v in vals)
        out.append((
            "前端「博主中心」下拉",
            has,
            f"缺 {vals} —— 搜博主后端可用但选不到（快手漏过）",
        ))

    # ---- B. 创作者中心不能串平台 ----
    #
    # 实测：`if (isXhs) {...} else {...抖音...}` —— else 无条件走抖音，
    # 选微博会显示**抖音的数据**。
    creator = _fe_file("pages/my-platform-data/CreatorCenterPanel.tsx")
    if creator and plat in ("weibo", "twitter", "bilibili"):
        # 不支持的平台应该"不加载"，而不是落到 else
        guarded = ("!isXhs && !isDouyin" in creator
                   or "!isDouyin && !isXhs" in creator)
        out.append((
            "创作者中心平台守卫",
            guarded,
            "不支持的平台要显式跳过，否则会显示**别的平台的数据**",
        ))

    # ---- C. 搜索分页要给 has_more ----
    #
    # 实测：X 从来没设 `_has_more` → 前端**永远显示"没有下一页"**，
    # 尽管后端 page=2/3 都能正常翻；B站/抖音/微博同样漏过。
    #
    # ⚠️ 要扫**整个平台目录** —— 搜索可能实现在
    # `search_api.py` / `search_http.py` / `search_patchright.py` /
    # `client.py` 任一处（微博就在 `search_patchright.py`，
    # 只扫前三个会漏判成"没实现"）。
    plat_dir = BACKEND_DIR / "app" / "services" / "platforms" / plat
    srcs: list[str] = []
    if plat_dir.is_dir():
        for p in sorted(plat_dir.glob("*.py")):
            try:
                srcs.append(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    if srcs and plat in _SEARCH_PAGED_PLATFORMS:
        joined = "\n".join(srcs)
        has_flag = "_has_more" in joined
        # 只对有搜索的平台要求
        if "def search" in joined or "async def search" in joined:
            out.append((
                "搜索结果带 has_more",
                has_flag,
                "不设的话前端**没有『下一页』**（X/B站/抖音都这样漏过）",
            ))

    return out


async def fetch_pg_enum() -> set[str] | None:
    """读取 PG 原生枚举 platformtype 的当前值；非 Postgres 或连不上返回 None。"""
    try:
        from sqlalchemy import text

        from app.db.database import get_async_session
    except Exception:
        return None

    try:
        async with get_async_session() as session:
            rows = await session.execute(
                text(
                    "SELECT enumlabel FROM pg_enum "
                    "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                    "WHERE pg_type.typname = 'platformtype'"
                )
            )
            return {r[0] for r in rows}
    except Exception as exc:  # 连不上库时不要伪装成"通过"
        print(f"  ! 无法连接数据库读取枚举：{type(exc).__name__}")
        return None


def main() -> int:
    load_env()

    parser = argparse.ArgumentParser(description="跨平台一致性检查")
    parser.add_argument(
        "platforms",
        nargs="*",
        help="只检查指定平台；留空则检查 SUPPORTED_PLATFORMS 全部",
    )
    parser.add_argument(
        "--allow-known",
        action="store_true",
        help="放行已知历史缺口（telegram/tiktok/twitter/youtube），仅检查其余平台",
    )
    args = parser.parse_args()

    model_src = read_text(BACKEND_DIR / "app" / "db" / "models" / "platform_connection.py")
    api_src = read_text(BACKEND_DIR / "app" / "api" / "v1" / "platforms.py")
    base_src = read_text(BACKEND_DIR / "app" / "services" / "cookies" / "base.py")
    reg_src = read_text(BACKEND_DIR / "app" / "services" / "cookies" / "platforms" / "__init__.py")
    fe_src = read_text(REPO_ROOT / "frontend" / "src" / "pages" / "accounts" / "index.tsx")

    py_types = extract_platform_types(model_src)
    supported = extract_supported_platforms(api_src)
    login_urls = extract_dict_keys(base_src, "PLATFORM_LOGIN_URLS")
    domains = extract_dict_keys(base_src, "PLATFORM_DOMAINS")
    test_urls = extract_dict_keys(base_src, "PLATFORM_TEST_URLS")
    detectors = extract_registry_keys(reg_src, "_detector_registry")
    fe_metas = extract_frontend_metas(fe_src)

    pg_enum = asyncio.run(fetch_pg_enum())

    targets = args.platforms or sorted(supported)
    if args.allow_known:
        targets = [t for t in targets if t not in KNOWN_GAPS]
    if not args.platforms:
        print(f"检查 {len(targets)} 个平台（SUPPORTED_PLATFORMS）\n")

    problems: list[str] = []
    for plat in targets:
        print(f"- {plat}")
        missing: list[str] = []

        # 1) Python 枚举（Postgres 用大写 name，天然要求是合法成员）
        if plat.upper() not in py_types:
            missing.append("PlatformType 枚举缺成员（DB 列依赖它）")

        # 2) PG 原生枚举（仅 Postgres）
        if pg_enum is not None and plat.upper() not in pg_enum:
            missing.append(
                "PG platformtype 枚举缺该值（需迁移 ALTER TYPE；缺则用该平台查库报 "
                "invalid input value for enum）"
            )

        # 3) 浏览器取 Cookie 三件套（UI-only 平台可豁免）
        if plat not in UI_ONLY_PLATFORMS:
            for label, keys in (
                ("PLATFORM_LOGIN_URLS", login_urls),
                ("PLATFORM_DOMAINS", domains),
                ("PLATFORM_TEST_URLS", test_urls),
            ):
                if plat not in keys:
                    missing.append(f"{label} 缺条目（Cookie 会退化/无法提取）")
            if plat not in detectors:
                missing.append("_detector_registry 缺检测器（点『浏览器』会报暂不支持）")

        # 4) 前端入口
        if plat not in fe_metas:
            missing.append("前端 PLATFORM_METAS 缺条目（账号中心看不到入口）")

        # 5) 能力层（2026-09-29 加）
        #
        # 上面 1-4 只保证"登记齐全"，**不保证功能真的接通**。
        # 这一节查的是"后端起效了但前端/其它层没接上"那类**不报错**的坑
        # （本轮实测踩了四个，症状都是"悄无声息地不对"）。
        for label, ok, hint in check_capability_layers(plat):
            if not ok:
                missing.append(f"{label} —— {hint}")

        if missing:
            print("  MISSING:")
            for m in missing:
                print(f"      - {m}")
            problems.append(f"{plat}: {len(missing)} 项")
        else:
            print("  OK: registers consistent")

    print()
    if problems:
        print(f"发现 {len(problems)} 个平台存在缺失：")
        for p in problems:
            print(f"  {p}")
        print("\n提示：新增平台务必同时改上述几处，否则会出现『业务可用但 UI 无入口』。")
        print("已知历史缺口（telegram/tiktok/twitter/youtube 缺 Detector 与前端入口，")
        print("本就未支持浏览器取 Cookie）：可用 --allow-known 临时放行，勿视为正常。")
        return 1

    print("All platform registers consistent OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
