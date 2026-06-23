from app.services.wechat_mp.parser import WechatMPParser


def test_extract_content_html_handles_nested_hidden_nodes():
    html = """
    <html>
      <head>
        <meta property="og:title" content="Parser regression" />
      </head>
      <body>
        <div id="js_content">
          <section style="display: none">
            <span style="visibility: hidden">hidden text</span>
          </section>
          <p>visible text</p>
        </div>
      </body>
    </html>
    """

    result = WechatMPParser().parse(html, "https://mp.weixin.qq.com/s/example")

    assert result["error"] == ""
    assert "visible text" in result["content_html"]
    assert "hidden text" not in result["content_html"]


def test_markdown_renderer_skips_empty_list_items():
    html = """
    <html>
      <body>
        <div id="js_content">
          <ul>
            <li><span></span></li>
            <li>real item</li>
          </ul>
        </div>
      </body>
    </html>
    """

    parser = WechatMPParser()
    result = parser.parse(html, "https://mp.weixin.qq.com/s/example")
    markdown = parser.to_markdown(result)

    assert "- real item" in markdown
    assert "- \n" not in markdown
