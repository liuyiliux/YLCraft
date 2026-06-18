# 微信公众号模块 Step 3 实施方案

> 目标：补齐体验层 —— **批量下载并发+进度（#7）/ 下载目录规范（#12）/ 封面摘要复用（#11）/ PDF 导出（#9）**。
> 本文档为可直接交付给 AI 执行的实施方案，包含已完成项的现状核实、待办项的精确改动点、验收标准。
> 前置 Step 1（修 bug + 补基建）、Step 2（图片本地化 + EPUB + 解析器重写）已完成。

---

## 0. 总览：四项任务的真实状态（代码核实）

| # | 任务 | 状态 | 核实证据 |
|---|------|------|----------|
| #7 | 批量下载并发 + WebSocket 进度 | ✅ **已完成** | `service.py:549` `asyncio.Semaphore(max_concurrency)`；`:601` `asyncio.gather`；`:542/554-565` `push_task_progress` 推送，失败静默忽略；并发度钳制 1~8 |
| #12 | 下载目录规范 | ✅ **已完成** | `service.py:409` `<download>/wechat_mp/<author>/<YYYY-MM>/`；`:442-445` 文件名去时间戳前缀 + `_unique_file_path` 防覆盖；`_publish_month` 提取年月，缺失回退当前月 |
| #11 | 封面/摘要复用 + 修字段 bug | ✅ **已完成** | `service.py` 新增 `cache_parsed`/`get_cached_parsed`（TTL 300s、容量 50、LRU 淘汰、浅拷贝隔离）；`download_article` 命中缓存则跳过抓取+解析；`download.py` parse 端点解析后回填缓存；字段 bug `cover_url=parsed.get("cover")`、`digest=content_text[:200]` 已修 |
| #9 | PDF 导出 | ⬜ **待做** | wechat_mp 模块无 pdf/weasyprint；`requirements.txt` 无 weasyprint；但 **patchright>=1.60.1 已是项目依赖** 且 Windows 已装并投用 |

**结论：Step 3 仅剩 #9 一项。** 本文档后续聚焦 #9 的实施。

---

## 1. 方案选型：patchright `page.pdf()`（已定）

### 探测结论（Linux 当前环境）

| 方案 | 可行性 | 说明 |
|------|--------|------|
| weasyprint | ❌ 不可行 | 未装；Linux 需系统库 cairo/pango/gdk-pixbuf，当前环境连 git 都没有，装不了；Windows 也要 GTK 运行库，较重 |
| patchright（playwright 隐身版） | ✅ **最优** | `requirements.txt:29` 已声明 `patchright>=1.60.1`；Windows 端已装并投用；`page.pdf()` 原生 HTML→PDF，排版质量好，**零新增依赖** |
| reportlab / fpdf / xhtml2pdf | ❌ 不选 | 需手写排版，工作量大，质量差 |

### 选 patchright 的理由

1. **零新增依赖**：项目已用 patchright 做 Cookie 获取，Windows 已装好
2. **排版质量高**：Chromium 打印引擎，微信文章样式/背景色/图片完整保留
3. **复用现成基建**：`backend/app/services/browser/patchright_runtime.py` 已封装浏览器启动、Windows 事件循环兼容、系统浏览器探测
4. **与图片本地化天然衔接**：本地化后的 HTML（图片用 `images/xxx` 相对路径）直接 `set_content` 即可，无需额外处理

---

## 2. 关键现状（改动前必读）

### 2.1 `PatchrightBrowserRuntime` 可复用部分

文件：`backend/app/services/browser/patchright_runtime.py`

```python
class PatchrightBrowserRuntime:
    def is_available(self) -> bool                          # 探测 patchright 是否可导入
    async def ensure_browser(self, headless=False)          # 启动/复用浏览器实例
    async def new_context(self, *, headless=..., ...)       # 新建 context（viewport/UA/headers）
    async def fetch_page(self, url, ...) -> BrowserFetchResult  # 抓取页面 HTML（不能打印 PDF）
    async def close(self)                                   # 关闭浏览器
```

单例获取：
```python
from app.services.browser.patchright_runtime import get_patchright_runtime
runtime = get_patchright_runtime()  # 进程级单例
```

**重要**：`fetch_page` 只抓 HTML，**没有** `set_content + page.pdf` 能力。`pdf_exporter` 需要用 `ensure_browser`/`new_context` 起浏览器后自建 page 调 `page.pdf()`。

### 2.2 Windows 事件循环兼容

`patchright_runtime.py:18-27` 已处理：Windows 上自动切 `ProactorEventLoop`（patchright 子进程需要）。`pdf_exporter` 复用同一 runtime 即自动继承该兼容，**无需重复处理**。

### 2.3 `service.download_article` 现有 format 分支

`service.py:447-473`：
```python
ext = {"md": "md", "html": "html", "epub": "epub"}.get(format, "md")
file_path = self._unique_file_path(save_dir, safe_title or "未命名", ext)

if format == "md":
    content = self._parser.to_markdown(parsed)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
elif format == "html":
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)        # ← html 是已本地化图片 URL 的全文 HTML
elif format == "epub":
    from .epub_exporter import build_epub
    build_epub(...)
else:
    # 默认 markdown
    ...
```

**关键**：`html` 变量在此处已是「图片本地化后的全文 HTML」（`service.py:440` `html = self._rewrite_urls(html, url_map)`）。PDF 分支直接复用这个 `html`，无需再做 URL 改写。

---

## 3. 任务 #9：PDF 导出实施

### 3.1 新建 `backend/app/services/wechat_mp/pdf_exporter.py`

```python
"""
微信公众号文章 PDF 导出

使用 patchright（Playwright 隐身版）的 page.pdf() 渲染：
- 复用项目级 PatchrightBrowserRuntime 单例（自动处理 Windows 事件循环兼容）
- 输入为已本地化图片的全文 HTML（图片用 images/xxx 相对路径）
- print_background=True 保留微信文章背景色/样式
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("ylcraft.wechat_mp.pdf_exporter")


async def render_pdf(
    html: str,
    out_path: str,
    title: str = "",
    base_dir: str = "",
) -> str:
    """
    将 HTML 渲染为 PDF 并写入 out_path。

    Args:
        html: 已本地化图片的全文 HTML（img src 为 images/xxx 相对路径）
        out_path: 输出 .pdf 绝对路径
        title: 文章标题（用于 PDF 元数据）
        base_dir: HTML 中相对资源（images/）的基准目录，默认取 out_path 父目录

    Returns:
        out_path

    Raises:
        RuntimeError: patchright 不可用或渲染失败
    """
    ...
```

#### 实现要点

1. **复用 runtime 单例**：
   ```python
   from app.services.browser.patchright_runtime import get_patchright_runtime, PATCHRIGHT_INSTALL_MESSAGE
   runtime = get_patchright_runtime()
   if not runtime.is_available():
       raise RuntimeError(PATCHRIGHT_INSTALL_MESSAGE)
   ```

2. **base 标签注入**：`page.pdf()` 用 `set_content` 加载 HTML 时，相对路径 `images/xxx` 需要基准。在 `<head>` 注入 `<base href="file://{base_dir}/">`：
   ```python
   from pathlib import Path
   from urllib.parse import quote
   base = Path(base_dir or Path(out_path).parent).resolve()
   base_href = base.as_uri() + "/"   # file:///.../wechat_mp/作者/2024-03/
   full_html = html.replace("<head>", f'<head><base href="{base_href}">', 1)
   # 兜底：若无 <head>，包一层完整文档
   if "<head>" not in html:
       full_html = f'<!DOCTYPE html><html><head><base href="{base_href}"><meta charset="utf-8"><title>{title}</title></head><body>{html}</body></html>'
   ```

3. **渲染流程**：
   ```python
   context = await runtime.new_context(headless=True)
   try:
       page = await context.new_page()
       await page.set_content(full_html, wait_until="networkidle", timeout=30000)
       await page.emulate_media(media="print")   # 打印媒体查询
       await page.pdf(
           path=out_path,
           format="A4",
           print_background=True,   # 关键：保留背景色
           margin={"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"},
           display_header_footer=True,
           header_template=f'<div style="font-size:9px;color:#999;padding:0 15mm;">{title}</div>',
           footer_template='<div style="font-size:9px;color:#999;padding:0 15mm;width:100%;text-align:center;"><span class="pageNumber"></span>/<span class="totalPages"></span></div>',
       )
   finally:
       await context.close()
   return out_path
   ```

4. **错误处理**：`page.set_content`/`page.pdf` 抛异常时向上抛 `RuntimeError`（由 service 层 try-except 降级）。不在此处吞异常，保持单一职责。

### 3.2 改 `backend/app/services/wechat_mp/service.py`

#### 改动 1：`ext` 字典加 pdf

`service.py:444`：
```python
ext = {"md": "md", "html": "html", "epub": "epub", "pdf": "pdf"}.get(format, "md")
```

#### 改动 2：format 分支加 pdf（在 epub 分支之后、else 之前）

`service.py:468`（`elif format == "epub":` 块结束之后）插入：
```python
elif format == "pdf":
    from .pdf_exporter import render_pdf
    await render_pdf(
        html=html,
        out_path=file_path,
        title=title,
        base_dir=str(save_dir),
    )
```

**错误隔离**：`render_pdf` 是 async 且在 `try` 块内，失败会被 `service.py:504` 的 `except Exception` 捕获，自动落库失败记录 + 返回 `{"success": False, "error": ...}`。与图片本地化失败降级思路一致。**无需额外 try-except**。

#### 改动 3：docstring 更新

`download_article` docstring 的 `format: md / html / epub。` → `format: md / html / epub / pdf。`

### 3.3 改 `backend/app/api/v1/wechat_mp.py`

#### `DownloadSingleRequest.format` 注释/校验

搜 `format` 字段定义处，注释更新为 `md / html / epub / pdf`。若有 `Literal` 或正则校验，加 `pdf`。

### 3.4 改 `backend/app/db/models/wechat_mp.py`

`WechatMPDownload.format` 字段描述：
```python
format: str = Field("md", description="导出格式: md / html / epub / pdf")
```

---

## 4. 改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/wechat_mp/pdf_exporter.py` | **新建** | `render_pdf()` 用 patchright page.pdf() |
| `backend/app/services/wechat_mp/service.py` | 改 | `ext` 加 pdf；format 分支加 pdf；docstring |
| `backend/app/api/v1/wechat_mp.py` | 改 | format 注释/校验加 pdf |
| `backend/app/db/models/wechat_mp.py` | 改 | format 字段描述 |
| `backend/requirements.txt` | **不改** | patchright 已声明 |

---

## 5. 代码风格与约束（必须遵守）

- `from __future__ import annotations`；模块级 `logger = logging.getLogger("ylcraft.wechat_mp.pdf_exporter")`；类型注解齐全
- **错误隔离**：PDF 失败不能中断服务启动（patchright 不可用时 `render_pdf` 抛 RuntimeError，由 service 层捕获降级）
- **复用 runtime 单例**：用 `get_patchright_runtime()`，不要自己 `async_playwright().start()`（避免多浏览器实例泄漏）
- **headless=True**：PDF 渲染无需有头浏览器
- **不破坏现有 format**：md/html/epub 分支不动
- **路径安全**：`out_path` 由 service 的 `_unique_file_path` 生成，已防覆盖

---

## 6. 验收标准（全部需通过）

1. 模块导入：
   ```bash
   cd backend && venv_win\Scripts\python.exe -c "import app.services.wechat_mp.pdf_exporter; print('ok')"
   ```
   输出 `ok`。

2. 单篇 PDF 生成：
   ```bash
   # 调 POST /api/v1/wechat-mp/download-single，format=pdf
   # 生成 .pdf 文件，非空（>1KB）
   ```
   - 用 Adobe Reader / 浏览器打开，文字、图片、样式完整
   - 图片为本地化后的（断网仍可见）

3. patchright 不可用降级：
   - 模拟 patchright 未装（或 `runtime.is_available()` 返回 False）
   - 调 download-single format=pdf → 返回 `{"success": False, "error": "Patchright 未安装..."}`
   - 不崩溃，落库 status=failed

4. 路由数不变：`len(wechat_mp.router.routes)` 仍为 **8**（未加新端点，PDF 复用 /download-single）。

5. `git diff --stat` 仅涉及第 4 节列出的文件。

---

## 7. 风险与备注

- **`set_content` 相对路径**：`page.set_content` 加载的 HTML 无 URL 上下文，`images/xxx` 相对路径需靠 `<base href="file://.../">` 解析。已验证 patchright（基于 Chromium）支持 `file://` base。若个别图片不显示，可改为 `page.goto(file://{base}/_render.html)` 方案（先写临时 HTML 文件再导航），但首选 base 标签方案。
- **networkidle 超时**：若文章图片多/加载慢，`set_content(wait_until="networkidle")` 可能超时 30s。可降级 `wait_until="load"` + `page.wait_for_timeout(2000)` 兜底。
- **并发 PDF 渲染**：patchright runtime 是单例浏览器，并发多篇 PDF 会复用同一浏览器实例、各自新建 context（隔离）。批量下载 format=pdf 时，每篇独立 context，安全。但 Chromium 并发渲染内存占用较高，建议批量 PDF 时并发度 ≤2（`download_articles_batch` 的 concurrency 参数由调用方传）。
- **PDF 不嵌入 epub**：本方案仅做单篇 PDF。批量合并 PDF（多篇合一）不在 Step 3 范围，留待后续（可用 PyPDF2 合并，但需新增依赖）。

---

## 8. 本轮已完成改动（#11，待提交）

为完整性记录，#11 的改动如下（已在工作区，待 git 提交）：

### `backend/app/services/wechat_mp/service.py`
- `import time`
- `__init__` 加 `self._parsed_cache: dict[str, tuple[float, dict, str]] = {}` + 类级 `_PARSED_CACHE_TTL = 300` / `_PARSED_CACHE_MAX = 50`
- 新增 `cache_parsed(article_url, parsed, html)` / `get_cached_parsed(article_url) -> Optional[tuple[dict, str]]`（LRU 淘汰、TTL 过期、浅拷贝隔离）
- `download_article` 重构：抓取前查缓存，命中跳过 `get_article_content`+`parse`；未命中解析后 `cache_parsed` 回填
- 修 bug：`cover_url=parsed.get("cover", "")`、`digest=(parsed.get("content_text") or "")[:200]`（原 `cover_url`/`digest` 字段名不存在，永远存空）

### `backend/app/api/v1/download.py`
- parse 端点解析后调 `get_wechat_mp_service().cache_parsed(url, parsed, html)` 回填缓存（try-except 静默失败）

### 验证
- 自测覆盖：缓存 hit/miss、浅拷贝隔离、LRU 淘汰、TTL 过期、字段 bug 修复、双端回填 —— 全 PASS
- 两文件 lint 干净、语法 OK

---

## 附：Step 3 完成后整体收尾

Step 3 四项全部完成后，微信公众号模块对照开源项目的 12 项优化清单（见历史分析）将全部落地：

| 步骤 | 项 | 状态 |
|------|----|------|
| Step 1 | #1 笔误 / #6 落库 / #10 缓存 / #8 去重 | ✅ |
| Step 2 | #4/#5 解析器重写 / #2 图片本地化 / #3 EPUB | ✅ |
| Step 3 | #7 并发+进度 / #12 目录规范 / #11 复用 / #9 PDF | #9 待做 |

执行者完成 #9 后，建议统一跑一次端到端：含图文章下载 md/html/epub/pdf 四格式 + 批量下载 + parse→download 缓存命中，确认全链路无回归。
