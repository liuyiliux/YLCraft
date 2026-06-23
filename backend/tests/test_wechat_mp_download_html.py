from app.services.wechat_mp.service import WechatMPService


def test_rewrite_urls_promotes_wechat_placeholder_src_to_local_image():
    remote = "https://mmbiz.qpic.cn/mmbiz_png/example/640?wx_fmt=png"
    html = (
        '<p><img class="rich_pages wxw-img js_img_placeholder" '
        'src="data:image/svg+xml,%3Csvg%3E" '
        f'data-src="{remote}" /></p>'
    )

    rewritten = WechatMPService._rewrite_urls(html, {remote: "images/001.png"})

    assert 'src="images/001.png"' in rewritten
    assert 'data-src="images/001.png"' in rewritten
    assert "data:image/svg+xml" not in rewritten
