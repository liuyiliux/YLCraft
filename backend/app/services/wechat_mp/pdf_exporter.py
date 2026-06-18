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
    from app.services.browser.patchright_runtime import (
        get_patchright_runtime,
        PATCHRIGHT_INSTALL_MESSAGE,
    )

    runtime = get_patchright_runtime()
    if not runtime.is_available():
        raise RuntimeError(PATCHRIGHT_INSTALL_MESSAGE)

    base = Path(base_dir or Path(out_path).parent).resolve()
    base_href = base.as_uri() + "/"

    if "<head>" in html:
        full_html = html.replace("<head>", f'<head><base href="{base_href}">', 1)
    else:
        full_html = f'<!DOCTYPE html><html><head><base href="{base_href}"><meta charset="utf-8"><title>{title}</title></head><body>{html}</body></html>'

    context = await runtime.new_context(headless=True)
    try:
        page = await context.new_page()
        await page.set_content(full_html, wait_until="networkidle", timeout=30000)
        await page.emulate_media(media="print")
        await page.pdf(
            path=out_path,
            format="A4",
            print_background=True,
            margin={"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"},
            display_header_footer=True,
            header_template=f'<div style="font-size:9px;color:#999;padding:0 15mm;">{title}</div>',
            footer_template='<div style="font-size:9px;color:#999;padding:0 15mm;width:100%;text-align:center;"><span class="pageNumber"></span>/<span class="totalPages"></span></div>',
        )
    finally:
        await context.close()

    logger.info(f"[pdf_exporter] PDF 生成成功: {out_path}")
    return out_path