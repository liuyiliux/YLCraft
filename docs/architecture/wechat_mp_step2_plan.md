# 微信公众号模块 Step 2 实施方案

> 目标：对齐开源项目（EasyWechatDownload / WeChatDownload）的核心能力 —— **图片本地化 + EPUB 导出 + 解析器用 BeautifulSoup 重写**。
> 本文档为可直接交付给 AI 执行的实施方案，包含背景、现状、精确改动点、验收标准。
> 前置 Step 1 已完成（笔误修复 / 缓存清理 / 下载落库 / aid 去重），见 `git log`。

---

## 0. 环境与依赖现状（venv_win 实测）

| 依赖 | 状态 | 用途 |
|------|------|------|
| `bs4` (beautifulsoup4) | ✅ 已装 | Step 2 解析器重写 |
| `lxml` | ✅ 已装 | bs4 解析后端 |
| `ebooklib` | ✅ 已装 | EPUB 导出 |
| `httpx` | ✅ 已装 | 图片下载（已有同步/异步客户端） |
| `requests` | ✅ 已装 | 图片下载（同步兜底） |
| `PIL` (Pillow) | ✅ 已装 | 图片格式探测/转码 |
| `weasyprint` | ❌ 未装 | PDF 导出（**Step 2 不做**，留到 Step 3） |
| `markdown` / `html2text` | ❌ 未装 | 不引入，HTML→MD 用自研解析逻辑 |

**结论：Step 2 无需新增任何依赖。** 虚拟环境：`backend/venv_win/Scripts/python.exe`。

---

## 1. 当前代码结构（改动前必读）

```
backend/app/services/wechat_mp/
├── api_client.py    # WechatMPAPIClient — 微信后台 API（登录/搜索/文章列表/内容）
├── parser.py        # WechatMPParser — 当前用纯正则解析（脆弱，待重写）
├── service.py       # WechatMPService — 业务编排（download_article 已支持落库+去重）
└── __init__.py

backend/app/db/models/wechat_mp.py    # WechatMPDownload 表（已存在）
backend/app/api/v1/wechat_mp.py       # 路由 + DownloadSingleResponse/BatchResponse
backend/app/core/config.py            # ensure_download_path() 返回下载根目录
```

### 关键现状（Step 1 后）

- `WechatMPParser.parse(html, article_url)` 返回 dict：`{title, author, publish_time, content_html, content_text, images, cover, source_url}`
- `WechatMPParser.to_markdown(parse_result)` → str
- `WechatMPService.download_article(...)` 签名：
  ```python
  async def download_article(self, conn_id, article_url, article_title="",
                             cookie="", format="md", download_dir="",
                             skip_if_exists=True) -> dict
  ```
  返回：`{success, file_path, file_size, format, title, author, parsed, record_id, skipped?}`
- 保存路径：`<download_dir>/wechat_mp/<safe_author>/<YYYYMMDD_HHMMSS>_<safe_title>.<ext>`
- **当前图片仍是远程 `mmbiz.qpic.cn` 链接**（未本地化）—— Step 2 重点修这个
- **当前只支持 md / html** —— Step 2 加 epub

---

## 2. 任务分解

### 任务 A：解析器用 BeautifulSoup 重写（parser.py）

**问题**：当前 `_extract_content_html` 用正则 `(.*?)</div>` 截断，遇到嵌套 div / 微信新版结构（`js_content` 带 `visibility:hidden`、`data-src`+`src` 双写）会丢内容；`_html_to_markdown` 用裸正则，不处理 `<pre>`/`<blockquote>`/`<table>`/微信卡片。

**改动**：在 `parser.py` 内**重写**以下方法，保持对外接口（`parse()` 返回字段、`to_markdown()` 签名）不变，避免 service 层改动：

1. `parse()`：内部改用 `BeautifulSoup(html, "lxml")`，soup 对象传给各子方法，正则仅作 meta 提取的兜底。
2. `_extract_content_html`：用 `soup.find("div", id="js_content")`，`.decode_contents()` 取原始 HTML；移除 `style="visibility:hidden"` 等隐藏样式（遍历 `[tag for tag in soup.find_all(True) if tag.get('style')]`，删 visibility/display:none 的节点）。
3. `_extract_images`：遍历 `soup.find_all("img")`，取 `data-src`（优先）→ `data-original` → `src`；过滤 `data:`/`avatar`/`icon`。
4. `_html_to_markdown`：**改成 BeautifulSoup 遍历**（不要继续用正则）。递归处理节点：
   - `<p>` → `\n\n` 分隔
   - `<h1>~<h6>` → `#`×n
   - `<strong>/<b>` → `**...**`
   - `<em>/<i>` → `*...*`
   - `<a href>` → `[text](href)`
   - `<img>` → `![图片](url)`（url 用本地化后的相对路径，由 service 注入）
   - `<pre>` → 代码块 ```` ```...``` ````
   - `<blockquote>` → `> ...`
   - `<table>` → markdown 表格（或退化为纯文本）
   - `<li>` → `- `（ul）/ `1. `（ol）
   - `<br>` → `\n`
   - 微信特有卡片（`<mpvoice>`, `<mpvideosnap>`, `<mp-common-mpaudio>`）→ 占位文本 `（音视频卡片）`
   - `<section>`：微信排版核心标签，**保留其子节点的文本和换行**，不输出 section 本身
5. `_strip_html`：用 `soup.get_text(separator=" ")`。

**验收**：对一篇真实微信文章 HTML，重写后的 `content_text` 字符数 ≥ 旧版的 95%（不丢内容）；`to_markdown` 输出包含正确的代码块/引用。

---

### 任务 B：图片本地化（新建 image_localizer.py + 改 service.py）

**目标**：下载文章时，把 `mmbiz.qpic.cn` 等微信 CDN 图片下载到本地，并改写 MD/HTML 里的 URL 为相对路径。

#### B1. 新建 `backend/app/services/wechat_mp/image_localizer.py`

```python
"""
微信公众号文章图片本地化
- 下载图片到 <save_dir>/images/<seq>_<hash>.<ext>
- 返回 {原URL: 相对路径} 映射，供 parser/service 改写
"""
from __future__ import annotations
import asyncio, hashlib, logging, os
from pathlib import Path
from typing import Optional
import httpx

logger = logging.getLogger("ylcraft.wechat_mp.image_localizer")

# 微信图片 CDN（防盗链宽松，但仍带 Referer 更稳）
_REFERER = "https://mp.weixin.qq.com/"
_CONCURRENCY = 3  # 并发下载数（遵守微信限流）


class ImageLocalizer:
    def __init__(self, save_dir: str, client: Optional[httpx.AsyncClient] = None):
        self.save_dir = Path(save_dir)
        self.images_dir = self.save_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self._client = client  # 可复用外部 client
        self._sem = asyncio.Semaphore(_CONCURRENCY)

    async def localize(self, image_urls: list[str]) -> dict[str, str]:
        """
        下载所有图片。返回 {原URL: 相对路径(相对 save_dir)}。
        失败的 URL 不出现在返回 dict 中（保持原 URL 不改写）。
        """
        ...

    def close(self): ...
```

**实现要点**：
- 用 `httpx.AsyncClient`（复用 api_client 已有的 client 实例更佳，但要传 `Referer` header）；超时 15s，失败重试 1 次。
- 文件名：`f"{idx:03d}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"`，idx 保证顺序。
- 扩展名：从 `Content-Type` 推断（`image/jpeg`→`.jpg`），PIL 探测兜底；拿不到则 `.jpg`。
- 返回的相对路径：`images/xxx.jpg`（相对 `save_dir`，便于 MD/HTML 引用）。
- 图片已是 `data:` URI 的跳过（不下载）。

#### B2. 改 `service.py` 的 `download_article`

在「2. 解析文章」之后、「4. 生成文件名」之前，插入图片本地化：

```python
# 2.5 图片本地化（可选，默认开启）
localize_images = True  # 可由参数传入
url_map = {}
if localize_images:
    from .image_localizer import ImageLocalizer
    localizer = ImageLocalizer(save_dir)
    try:
        url_map = await localizer.localize(parsed.get("images", []))
    finally:
        localizer.close()
    # 改写 content_html / markdown 里的 URL
    if url_map:
        parsed["content_html"] = self._rewrite_urls(parsed["content_html"], url_map)
```

**URL 改写**：新增辅助方法 `WechatMPService._rewrite_urls(html, url_map)` —— 对每个 `原URL→相对路径`，做字符串替换（HTML 和 markdown 文本都适用）。同时更新 `parsed["images"]` 为本地路径列表。

**MD 输出**：`to_markdown` 里的图片标签已用改写后的 content_html，自动生效。
**HTML 输出**：写文件前对 `html` 做同样的 URL 替换。

#### B3. 落库

`WechatMPDownload` 表已有 `cover_url` 字段。封面图也走本地化（如果有），存相对路径。无需改表结构。

**验收**：下载一篇含图文章后，`<save_dir>/images/` 下有真实图片文件；打开生成的 .md，图片用相对路径且能正常显示；断网后 md 仍可看图。

---

### 任务 C：EPUB 导出（新建 epub_exporter.py + 改 service.py）

**目标**：支持 `format="epub"`，单篇导出 EPUB；批量下载提供一个「合并多篇为 EPUB」入口。

#### C1. 新建 `backend/app/services/wechat_mp/epub_exporter.py`

用 `ebooklib`：

```python
"""
微信公众号文章 EPUB 导出
- 单篇：标题=书名，正文=一个章节
- 多篇合并：书名=公众号名/自定义，每篇一个章节
"""
from __future__ import annotations
import logging
from pathlib import Path
from ebooklib import epub

logger = logging.getLogger("ylcraft.wechat_mp.epub_exporter")


def build_epub(
    book_title: str,
    articles: list[dict],          # [{title, author, publish_time, content_html, source_url}]
    out_path: str,
    cover_image_path: str = "",    # 可选封面图绝对路径
) -> str:
    """
    构建 EPUB。
    - content_html 应为已本地化图片的 HTML（图片用 <img src="images/xxx">）
    - 自动把 images/ 下的图片加入 EPUB 资源
    返回 out_path。
    """
    ...
```

**实现要点**：
- `epub.EpubBook()`，设 `set_title/set_language('zh-CN')/add_author`。
- 每篇文章：`epub.EpubHtml(title=..., file_name=f"chap_{i}.xhtml")`，`set_content(content_html)`，`book.add_item(chap)`。
- 目录：`book.toc = (chapters...)` + `add_item(EpubNcx())` + `add_item(EpubNav())`。
- 图片资源：扫 content_html 里的 `images/xxx`，用 `epub.EpubImage` 加 `book.add_item`，`media_type` 从扩展名推断。
- 封面：若有 `cover_image_path`，`book.set_cover("image.jpg", open(...).read())`。
- `epub.write_epub(out_path, book, {})`。

#### C2. 改 `service.py`

1. `download_article` 的 format 分支新增 `epub`：
   ```python
   elif format == "epub":
       from .epub_exporter import build_epub
       file_path = str(save_dir / f"{timestamp}_{safe_title}.epub")
       build_epub(
           book_title=title,
           articles=[{
               "title": title,
               "author": author,
               "publish_time": parsed.get("publish_time", ""),
               "content_html": parsed.get("content_html", ""),
               "source_url": article_url,
           }],
           out_path=file_path,
           cover_image_path=parsed.get("cover_local_path", ""),
       )
   ```

2. 新增方法 `export_batch_to_epub(conn_id, articles_records, book_title, out_path)`：
   - `articles_records`：已下载文章的 parsed 结果列表（含本地化后的 content_html）
   - 调 `build_epub` 合并
   - 落库一条 `WechatMPDownload` 记录（`article_url` 用合成 key 如 `epub:<book_title>`，`format=epub`）

#### C3. API 层（api/v1/wechat_mp.py）

- `DownloadSingleRequest.format` 注释更新为 `md / html / epub`。
- 新增端点 `POST /export-epub`：
  ```python
  class ExportEpubRequest(BaseModel):
      conn_id: str
      article_urls: list[str]       # 已下载文章的 URL（从落库记录取 parsed）
      book_title: str
      download_dir: str = ""

  @router.post("/export-epub", summary="多篇已下载文章合并导出 EPUB")
  async def export_epub(req: ExportEpubRequest): ...
  ```
  - 实现：按 article_urls 查 `WechatMPDownload` 表取 file_path → 重新解析（或缓存 parsed）→ 调 service.export_batch_to_epub。
  - **简化方案**：直接接受前端传的 articles（title+content_html），不查库，避免重复解析。

**验收**：单篇 epub 能在 Apple Books / Calibre 打开，目录正确，图片显示；多篇合并 epub 章节顺序正确。

---

## 3. 改动文件清单（给执行者的 checklist）

| 文件 | 操作 | 任务 |
|------|------|------|
| `backend/app/services/wechat_mp/parser.py` | 重写解析方法（保持接口） | A |
| `backend/app/services/wechat_mp/image_localizer.py` | **新建** | B |
| `backend/app/services/wechat_mp/epub_exporter.py` | **新建** | C |
| `backend/app/services/wechat_mp/service.py` | `download_article` 插入图片本地化 + epub 分支；新增 `_rewrite_urls`、`export_batch_to_epub` | B, C |
| `backend/app/api/v1/wechat_mp.py` | format 注释；新增 `/export-epub` 端点 + 请求/响应模型 | C |
| `backend/app/db/models/wechat_mp.py` | **不改**（现有字段足够） | — |
| `backend/requirements.txt`（或等效依赖文件） | **不改**（依赖已齐） | — |

---

## 4. 代码风格与约束（必须遵守）

- **匹配现有风格**：`from __future__ import annotations`；模块级 `logger = logging.getLogger("ylcraft.wechat_mp.xxx")`；方法带中文 docstring；类型注解齐全。
- **错误隔离**：图片本地化 / epub 导出的失败**不能中断主下载流程**，用 try-except 包裹，失败记 warning，降级（图片保持远程链接、epub 失败返回 error）。
- **限流**：图片下载并发 ≤3（微信敏感）；复用 `WechatMPAPIClient._throttle` 的思路。
- **路径安全**：`safe_author`/`safe_title` 的字符过滤逻辑沿用 service.py 现有写法。
- **落库**：epub 导出也要落 `wechat_mp_downloads` 表（article_url 用 `epub:<title>`），便于历史/去重。
- **不破坏 Step 1**：去重（skip_if_exists）、落库（_record_download）逻辑保留。

---

## 5. 验收标准（全部需通过）

1. `cd backend && venv_win\Scripts\python.exe -c "import app.services.wechat_mp.image_localizer, app.services.wechat_mp.epub_exporter; from app.services.wechat_mp.parser import WechatMPParser; print('import ok')"` 输出 `import ok`。
2. 用一篇真实微信文章 HTML 喂给 `WechatMPParser().parse()`，`content_text` 长度 ≥ 旧版 95%，`to_markdown` 含至少一个代码块或引用（如原文有）。
3. 调 `POST /api/v1/wechat-mp/download-single`（format=md）下载含图文章，`<save_dir>/images/` 有图片，md 内图片为相对路径。
4. 调 `POST /api/v1/wechat-mp/download-single`（format=epub）成功生成 .epub，Calibre 能打开。
5. 调 `POST /api/v1/wechat-mp/export-epub` 合并 2+ 篇文章成功，章节顺序正确。
6. `git diff --stat` 仅涉及第 3 节列出的文件。
7. 路由加载：`from app.api.v1 import wechat_mp; len(wechat_mp.router.routes)` 应为 **8**（原 7 + export-epub）。

---

## 6. 风险与备注

- **微信图片防盗链**：带 `Referer: https://mp.weixin.qq.com/` 一般能下；若个别图 403，跳过保留原 URL（不阻塞）。
- **EPUB 图片路径**：ebooklib 要求 `img src` 相对 xhtml 文件；本地化时统一用 `images/xxx`，写入 epub 时 ebooklib 自动处理。执行者需实测。
- **content_html 本地化时机**：在 service 层改写（不在 parser），因为 parser 不应感知文件系统。parser 只负责结构化，service 负责落地。
- **可选优化（不在 Step 2 范围）**：PDF 导出（需 weasyprint）、批量下载并发+进度（Step 3）、WebSocket 进度推送（Step 3）。

---

## 附：相关开源项目参考

- EasyWechatDownload（图片本地化 + 多篇合并 EPUB 的产品形态）
- WeChatDownload（BeautifulSoup 解析微信文章的成熟实现，可参考其 `_html_to_markdown` 节点遍历策略）

执行者应先读 `backend/app/services/wechat_mp/service.py` 的 `download_article` 完整实现，再动手。
