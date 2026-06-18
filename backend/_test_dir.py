"""#12 下载目录规范化端到端自测"""
import asyncio
import os
import tempfile

from app.services.wechat_mp.service import WechatMPService

svc = WechatMPService()


class FakeClient:
    async def get_article_content(self, url):
        return {"html": "<html></html>", "status_code": 200}


svc._get_client = lambda *a, **k: FakeClient()

_parsed = {
    "title": "测试文章", "author": "测试作者",
    "publish_time": "2024-03-15 12:30:00",
    "content_html": "<p>hello</p>", "content_text": "hello",
    "images": [], "cover": "", "source_url": "",
    "article_url": "http://x/a1", "error": "",
}


class FakeParser:
    def parse(self, html, url):
        return dict(_parsed)

    def to_markdown(self, p):
        return "# 测试文章\n\nhello"


svc._parser = FakeParser()

errs = []


def chk(cond, msg):
    if not cond:
        errs.append(msg)


with tempfile.TemporaryDirectory() as d:
    # 第一次下载
    r = asyncio.run(svc.download_article(
        conn_id="c1", article_url="http://x/a1",
        article_title="测试文章", format="md",
        download_dir=d, skip_if_exists=False, localize_images=False,
    ))
    chk(r.get("success"), f"第一次下载失败: {r}")
    fp = r.get("file_path", "")
    chk(fp, "file_path 为空")
    chk(os.path.join("wechat_mp", "测试作者", "2024-03") in fp, f"目录结构不符: {fp}")
    chk(fp.endswith("测试文章.md"), f"文件名不符(应无时间戳前缀): {fp}")
    chk(os.path.exists(fp), f"文件未生成: {fp}")
    # 不应含下载时间戳前缀（旧格式 20240101_120000_）
    fname = os.path.basename(fp)
    chk(not fname[0:8].isdigit(), f"文件名仍含时间戳前缀: {fname}")

    # 第二次同名（不同 url 避免 skip）→ _2
    _parsed["article_url"] = "http://x/a2"
    r2 = asyncio.run(svc.download_article(
        conn_id="c1", article_url="http://x/a2",
        article_title="测试文章", format="md",
        download_dir=d, skip_if_exists=False, localize_images=False,
    ))
    chk(r2.get("success"), f"第二次下载失败: {r2}")
    chk(r2["file_path"].endswith("测试文章_2.md"), f"同名去重不符: {r2['file_path']}")
    chk(os.path.exists(r2["file_path"]), f"第二文件未生成: {r2['file_path']}")

    # 无 publish_time → 回退当前年月
    _parsed["article_url"] = "http://x/a3"
    _parsed["publish_time"] = ""
    r3 = asyncio.run(svc.download_article(
        conn_id="c1", article_url="http://x/a3",
        article_title="无日期文章", format="md",
        download_dir=d, skip_if_exists=False, localize_images=False,
    ))
    import datetime as _dt
    cur_ym = _dt.datetime.now().strftime("%Y-%m")
    chk(cur_ym in r3["file_path"], f"无 publish_time 未回退当前年月: {r3['file_path']}")

if errs:
    print("FAIL:")
    for e in errs:
        print("  -", e)
    raise SystemExit(1)
print("PASS: 目录规范化 + 同名去重 + 无日期回退")
