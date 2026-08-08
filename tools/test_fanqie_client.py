"""
番茄小说 FanqieClient 测试脚本（带安全护栏）

设计护栏（务必遵守）：
  - 默认只跑「离线单元测试」（markdown 转换 / cookie 解析 / 错误分类），不触网。
  - 真实接口调用（--live）必须显式开启，且：
      1. cookie 只能从「文件 / 环境变量 FANQIE_COOKIE」读取，绝不读取项目数据库；
      2. 标题强制包含 [TEST]，防止误覆盖线上章节；
      3. item_id / book_id / volume_id 必须由调用者通过参数显式传入独立测试章，
         本脚本不会自动建章，默认拒绝在未提供测试章时写入。
  - 真实调用失败时只打印错误类型（含 CookieExpiredError 提示），不静默重试。

用法：
  # 仅离线单元测试
  python tools/test_fanqie_client.py

  # 真实调用（需先准备一个独立的 [TEST] 番茄章节）
  python tools/test_fanqie_client.py --live \
      --cookie-file /path/to/fanqie_cookie.txt \
      --book-id 7669027234765622296 \
      --volume-id 7669027236615293976 \
      --item-id 7669027240289518104
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile

# 允许以脚本形式直接运行（把 backend 加到 sys.path）
_BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, os.path.abspath(_BACKEND))

from app.services.platforms.fanqie.utils import (  # noqa: E402
    markdown_to_fanqie_html,
    normalize_cookie,
    parse_netscape_cookie,
    classify_fanqie_error,
    CookieExpiredError,
    ParamError,
    RiskControlError,
    FanqieError,
)
from app.services.platforms.fanqie.apis import (  # noqa: E402
    DEFAULT_AID,
    DEFAULT_APP_NAME,
    COVER_ARTICLE,
    DOUYIN_HOT_LIST,
)


# =============================================================================
# 离线单元测试（不触网）
# =============================================================================

def test_markdown_to_fanqie_html() -> None:
    # 单段
    assert markdown_to_fanqie_html("hello") == "<p>hello</p>"
    # 双换行分段
    out = markdown_to_fanqie_html("a\n\nb")
    assert out == "<p>a</p><p>b</p>", out
    # 行内换行 → <br>
    out = markdown_to_fanqie_html("a\nb")
    assert out == "<p>a<br>b</p>", out
    # HTML 转义
    out = markdown_to_fanqie_html("<script>x</script>")
    assert "<script>" not in out and "&lt;script&gt;" in out, out
    # 粗体
    out = markdown_to_fanqie_html("**bold**")
    assert "<strong>bold</strong>" in out, out
    print("  [OK] markdown_to_fanqie_html")


def test_normalize_cookie() -> None:
    # 原始格式去空白
    assert normalize_cookie(" a=1 ; b=2 ") == "a=1; b=2"
    # Netscape 格式
    ns = "# Netscape HTTP Cookie File\nfanqienovel.com\tFALSE\t/\tFALSE\t0\tsessionid\tabc123\n"
    header = normalize_cookie(ns)
    assert header == "sessionid=abc123", header
    print("  [OK] normalize_cookie")


def test_parse_netscape_cookie() -> None:
    ns = "# comment\nx.com\tFALSE\t/\tFALSE\t0\tk\tv1\nx.com\tFALSE\t/\tFALSE\t0\tk2\tv2\n"
    d = parse_netscape_cookie(ns)
    assert d == {"k": "v1", "k2": "v2"}, d
    print("  [OK] parse_netscape_cookie")


def test_classify_error() -> None:
    e = classify_fanqie_error(-100, "用户未登录")
    assert isinstance(e, CookieExpiredError), type(e)
    e = classify_fanqie_error(-1, "参数 book_id 缺失")
    assert isinstance(e, ParamError), type(e)
    e = classify_fanqie_error(-1, "内容触发风控")
    assert isinstance(e, RiskControlError), type(e)
    e = classify_fanqie_error(500, "服务器开小差")
    assert isinstance(e, FanqieError) and not isinstance(e, (CookieExpiredError, ParamError, RiskControlError)), type(e)
    print("  [OK] classify_fanqie_error")


def run_offline_tests() -> None:
    print("=== 离线单元测试 ===")
    test_markdown_to_fanqie_html()
    test_normalize_cookie()
    test_parse_netscape_cookie()
    test_classify_error()
    print("All offline tests passed")


# =============================================================================
# 真实接口测试（带护栏）
# =============================================================================

TEST_TITLE_MARK = "[TEST]"


def _load_cookie(args) -> str:
    if args.cookie_file:
        with open(args.cookie_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    env = os.environ.get("FANQIE_COOKIE")
    if env:
        return env.strip()
    return ""


async def run_live_tests(args) -> None:
    cookie = _load_cookie(args)
    if not cookie:
        print("[SKIP] 未提供 cookie（--cookie-file 或环境变量 FANQIE_COOKIE），跳过真实测试")
        return

    # 护栏：真实写入必须有独立测试章的三段 ID
    if not (args.book_id and args.volume_id and args.item_id):
        print("[BLOCKED] 缺少 --book-id / --volume-id / --item-id（必须是你手动建好的独立 [TEST] 测试章），拒绝写入")
        return

    # 护栏：标题强制 [TEST]
    title = args.title or f"{TEST_TITLE_MARK} 自动测试章"
    if TEST_TITLE_MARK not in title:
        title = f"{TEST_TITLE_MARK} {title}"

    from app.services.platforms import create_client
    from app.services.platforms.types import ClientConfig, ClientMode

    config = ClientConfig(platform="fanqie", mode=ClientMode.API, cookie=cookie)
    client = create_client("fanqie", config)

    async with client:
        # 1) 只读：热榜
        print("\n--- get_hot_list (只读) ---")
        try:
            hot = await client.get_hot_list()
            print(f"  返回 data 顶层 keys: {list(hot.keys()) if isinstance(hot, dict) else type(hot)}")
            print("  [OK] 热榜接口可达")
        except FanqieError as e:
            print(f"  [ERROR] 热榜失败: {type(e).__name__}: {e}")

        # 2) 写入：存草稿（仅 [TEST] 测试章）
        print("\n--- save_draft (写入，仅 [TEST] 测试章) ---")
        try:
            data = await client.save_draft_from_markdown(
                book_id=args.book_id,
                item_id=args.item_id,
                title=title,
                content_markdown="# 这是自动测试草稿\n\n由 YLCraft FanqieClient 生成，可安全删除。",
                volume_name=args.volume_name or "第一卷：默认",
                volume_id=args.volume_id,
            )
            print(f"  返回 data: {json.dumps(data, ensure_ascii=False)[:500]}")
            print(f"  [OK] save_draft 成功（latest_version={data.get('latest_version')}）")
        except CookieExpiredError as e:
            print(f"  [ERROR] Cookie 失效，请重新登录番茄并刷新 cookie: {e}")
        except FanqieError as e:
            print(f"  [ERROR] save_draft 失败: {type(e).__name__}: {e}")


# =============================================================================
# 入口
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="番茄 FanqieClient 测试（带安全护栏）")
    parser.add_argument("--live", action="store_true", help="开启真实接口调用（默认仅离线测试）")
    parser.add_argument("--cookie-file", help="番茄 cookie 文件路径（仅本地，不入库）")
    parser.add_argument("--book-id", help="独立 [TEST] 测试章所属 book_id")
    parser.add_argument("--volume-id", help="独立 [TEST] 测试章所属 volume_id")
    parser.add_argument("--item-id", help="独立 [TEST] 测试章 item_id（必须是手动建好的空测试章）")
    parser.add_argument("--volume-name", help="卷名（默认「第一卷：默认」）")
    parser.add_argument("--title", help="章节标题（将强制包含 [TEST]）")
    args = parser.parse_args()

    run_offline_tests()

    if args.live:
        print("\n=== 真实接口测试（--live）===")
        asyncio.run(run_live_tests(args))


if __name__ == "__main__":
    main()
