"""图片代理的回归测试（2026-10-02）。

## 用户反馈

> "192.168.18.73:3000 我手机局域网访问这台电脑启动的项目，然后搜索图片都是看不了的"

## 两个独立原因（都不是"手机/局域网"造成的）

1. **后端没监听局域网**：README 写的是 `--host 127.0.0.1`，只绑定回环。
   图片走相对路径 `/api/v1/proxy/image` 由 vite 转发到本机后端，
   后端不通时浏览器**只画破图图标、不给任何提示**，
   于是被误读成"平台防盗链拦了跨网访问"。

2. **`proxyImageUrl` 用白名单，只代理 6 个域名**（真正的"假支持"）：
   白名单外的平台让浏览器直连 CDN，而**微博 `sinaimg.cn` 裸请求就是 403**
   （实测：裸 403 / 带 Referer 403 / 经后端代理 200）。
   也就是说微博封面**在电脑上也一直是破的**，与手机无关。

## 修复

* 后端启动命令 `--host 0.0.0.0`，README 增加局域网排查顺序。
* `proxyImageUrl` 改为**默认代理所有远程图**，只放行 `data:`/`blob:`/相对路径。
* 图片加载失败显示可读占位块，而不是浏览器默认破图图标。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
CRAWLER = FRONTEND / "pages" / "crawler" / "index.tsx"
BILI = FRONTEND / "components" / "bilibili" / "index.tsx"
README = Path(__file__).resolve().parents[2] / "README.md"
PROXY_API = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "proxy.py"


def _src(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"{path.name} not found")
    return path.read_text(encoding="utf-8", errors="ignore")


def _strip_comments_and_strings(text: str) -> str:
    """去掉**注释**，保留字符串与正则字面量。

    ⚠️ 试过用正则模拟 JS 的词法分析，结果把要断言的
    `if (!/^https?:\\/\\//i.test(url))` 里的 `//` 当成行注释，
    函数体被截断、断言永远失败（连续踩了两次）。
    所以这里**只去注释、保留字符串**：断言里改用「剥离注释后仍存在」
    的方式判断，白名单域名/代理路径这些关键字本来就写在字符串里，
    保留它们反而更准确。
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)//[^\n]*$", lambda m: m.group(0) if "/^https" in m.group(0) else "", text)
    return text


def _func_body(src: str, name: str) -> str:
    """抽出指定函数的源码体。

    ⚠️ **不能用花括号配平**：TSX 里 JSX 的 `<div>` / `<Image />` 不带花括号，
    配平会一直吃到后面别的代码，导致断言失真（实测：断言被"稀释"到 15 项里
    只失败 1 项）。

    改为切到**下一个顶层声明**（行首的 `function` / `export` / `const`）为止。
    """
    m = re.search(r"^function\s+" + re.escape(name) + r"\b", src, re.M)
    assert m, f"找不到函数 {name}"
    start = m.start()
    rest = src[m.end() :]
    nxt = re.search(r"(?m)^(?:function|export|const|class)\s", rest)
    return src[start:] if not nxt else src[start : m.end() + nxt.start()]


def _proxy_fn(path: Path) -> str:
    """抽出 proxyImageUrl 的函数体（去注释去字符串）。"""
    code = _strip_comments_and_strings(_src(path))
    m = re.search(r"function\s+proxyImageUrl\s*\([^)]*\)\s*(?::[^{]+)?\{", code)
    assert m, f"{path.name} 里找不到 proxyImageUrl"
    start = m.end() - 1
    depth, i = 0, start
    while i < len(code):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return code[start : i + 1]
        i += 1
    return code[start:]


# =============================================================================
# 回归 1：不能再用白名单
# =============================================================================

@pytest.mark.parametrize(
    "path, label",
    [(CRAWLER, "crawler/index.tsx"), (BILI, "components/bilibili/index.tsx")],
)
def test_proxy_image_url_has_no_domain_allowlist(path: Path, label: str):
    """不能再出现「只代理某几个域名、其余直连」的白名单判定。

    微博 `sinaimg.cn` 裸请求 403，白名单外的域名直连必破图。

    ⚠️ 判据要精确：函数里**允许**出现 xhscdn.com —— 它用于给小红书
    拼 `imageView2` 缩略图参数（实测省 200 倍流量），与"要不要代理"无关。
    真正要禁止的是**用域名判断来决定是否代理**：
      url.includes('xxx') && ... → 决定 return url（直连）
    """
    body = _proxy_fn(path)
    for domain in ("hdslb.com", "sinaimg.cn", "biliimg.com", "douyincdn.com", "qpic.cn"):
        assert domain not in body, (
            f"{label} 的 proxyImageUrl 仍对 {domain} 做白名单判断 —— "
            f"白名单外的平台会直连 CDN 并因防盗链破图（微博实测 403）"
        )
    # 禁止「命中域名就直连」的形态：includes(...) 后面直接 return url
    assert not re.search(r"includes\([^)]*\)\s*\)\s*(?:&&[^\n{]*)?return\s+url", body), (
        f"{label} 仍有「命中某域名就 return url 直连」的分支"
    )


@pytest.mark.parametrize(
    "path, label",
    [(CRAWLER, "crawler/index.tsx"), (BILI, "components/bilibili/index.tsx")],
)
def test_proxy_image_url_proxies_all_remote_urls(path: Path, label: str):
    """远程 http(s) 图必须走代理。"""
    body = _proxy_fn(path)
    assert re.search(r"https\?", body), (
        f"{label} 的 proxyImageUrl 没有按 /^https?:\\/\\//i 判定远程图 —— "
        f"应「默认代理远程图」，而不是按域名白名单挑"
    )


@pytest.mark.parametrize(
    "path, label",
    [(CRAWLER, "crawler/index.tsx"), (BILI, "components/bilibili/index.tsx")],
)
def test_proxy_image_url_keeps_local_urls_untouched(path: Path, label: str):
    """data:/blob:/相对路径必须原样返回，否则代理它们必然失败。"""
    body = _proxy_fn(path)
    # 非远程地址直接 return url（没有再拼代理前缀）
    assert "return url" in body, f"{label} 缺少「非远程地址原样返回」的保护"


@pytest.mark.parametrize(
    "path, label",
    [(CRAWLER, "crawler/index.tsx"), (BILI, "components/bilibili/index.tsx")],
)
def test_proxy_image_url_is_idempotent(path: Path, label: str):
    """已经是代理地址的不能再代理一次，否则 url 被 encode 两次必 400。"""
    body = _proxy_fn(path)
    assert "/api/v1/proxy/image" in body and "startsWith" in body, (
        f"{label} 的 proxyImageUrl 缺少幂等保护（重复代理会双重 encode）"
    )


# =============================================================================
# 回归 2：失败要有可读提示，不能是浏览器默认破图图标
# =============================================================================

def test_image_failure_shows_readable_placeholder():
    src = _src(CRAWLER)
    assert "image-fallback" in src, "缺少图片失败占位块"
    assert "图片加载失败" in src, "占位块没有可读文案"
    # 占位块必须挂在 onError 上（否则永远不会触发）
    assert "onError" in src, "占位块没有接 onError"


def test_cover_column_does_not_double_request_each_image():
    """封面不能为了探测而额外发一次图片请求。

    曾用两种都会重复请求的写法（都实测过，都已弃用）：
      1. 可见 antd Image + **隐藏探测 <img>** → YouTube 一屏 10 条多 10 次请求
      2. 可见原生 <img> + **隐藏 antd Image** 做受控预览 → 同样多发一次
    正确做法：antd `Image` **本身就有 `onError`**（透传给 rc-image），
    直接用官方能力即可，不需要任何隐藏图。
    """
    src = _src(CRAWLER)
    assert "cover-probe" not in src, (
        "封面列仍在用隐藏探测图，会让每张封面发两次请求"
    )
    # 不能有第二张隐藏的 Image（display:'none' 的 img 仍会发请求）
    assert not re.search(r"style=\{\{\s*display:\s*'none'\s*\}\}", src), (
        "仍有 display:'none' 的隐藏图片 —— 它照样会发请求，等于每张封面两次"
    )


def test_cover_uses_antd_onerror_not_custom_probe():
    """封面必须走 antd `Image` 自带的 `onError`，不要自己造探测机制。

    ⚠️ 我一度在注释里写"antd `Image` 不暴露 `onError`" —— **是错的**，已核实：
    antd 把除 `prefixCls/preview/className/style/fallback` 外的 props 透传
    给 `rc-image`，rc-image 内部既把 `onError` 挂到 `<img>`，也有自己的
    `useStatus`（会加 `-error` class、支持 `placeholder`/`fallback`）。
    """
    src = _src(CRAWLER)
    body = _func_body(src, "CoverCellImage")
    assert "onError" in body, "CoverCellImage 没有接 onError"
    # ⚠️ 必须锚定 `<Image` **后面接换行/空格**：只写 "<Image" 会被
    #    `<ImageFallback` 命中，变异体（用隐藏 <img> 探测）也能蒙混过关
    #    —— 实测变异后 15 项里只失败 1 项，就是被这个宽松匹配放过的。
    assert re.search(r"<Image[\s\n]", body), (
        "CoverCellImage 应直接用 antd `<Image>`（自带 onError 与点击预览），"
        "而不是 `<img>` + 自造探测"
    )
    # 不该出现原生 <img>
    assert re.search(r"<img[\s\n]", body) is None, (
        "CoverCellImage 不应再出现原生 <img>（应交给 antd Image）"
    )
    # 不该再出现"受控 preview"这类的自造机制
    assert "previewOpen" not in body, (
        "CoverCellImage 仍在自己控制 preview —— antd Image 自带点击预览，不需要"
    )


# =============================================================================
# 回归 3：后端必须能被局域网访问
# =============================================================================

def test_readme_backend_binds_all_interfaces():
    """README 的启动命令不能是 --host 127.0.0.1（只监听回环，手机访问不到）。"""
    readme = _src(README)
    bad = re.findall(r"uvicorn[^\n]*--host\s+127\.0\.0\.1[^\n]*", readme)
    assert not bad, f"README 仍让后端只监听回环：{bad}"


def test_readme_documents_lan_troubleshooting():
    """README 要有局域网访问的排查顺序（否则下一个人还会踩同一个坑）。"""
    readme = _src(README)
    assert "192.168" in readme
    assert "proxy/image" in readme, "README 未说明图片走代理，排查时无从下手"


def test_proxy_api_supports_antireferer_hosts():
    """后端代理必须带 Referer，否则 weibo/sinaimg 这类源站必 403。"""
    src = _src(PROXY_API)
    assert "sinaimg.cn" in src, "后端代理缺少 sinaimg.cn 的 Referer 映射（微博封面会 403）"
    assert "Referer" in src
