import pytest

from app.services.wechat_mp.api_client import WechatMPAPIClient
from app.services.wechat_mp.service import WechatMPService


class DummyResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


@pytest.mark.asyncio
async def test_search_global_articles_parses_copyright_response(monkeypatch):
    client = WechatMPAPIClient(cookie_str="session=ok", token="123")

    async def fake_throttle():
        return None

    async def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert "check_appmsg_copyright_stat" in url
        assert kwargs["data"]["url"] == "测试"
        assert kwargs["data"]["count"] == "10"
        return DummyResponse({
            "base_resp": {"ret": 0, "err_msg": "ok"},
            "total": 10000,
            "list": [{
                "title": "测试标题",
                "url": "http://mp.weixin.qq.com/s?__biz=abc&mid=123&idx=1&sn=xx#rd",
                "cover_url": "https://mmbiz.qpic.cn/cover.jpg",
                "digest": "",
                "content": "<p>正文内容</p>",
                "nickname": "测试号",
                "author": "作者",
            }],
        })

    monkeypatch.setattr(client, "_throttle", fake_throttle)
    monkeypatch.setattr(client, "_request", fake_request)

    result = await client.search_global_articles("测试", count=50)

    assert result["total"] == 10000
    assert result["list"][0]["aid"] == "abc_123_1"
    assert result["list"][0]["title"] == "测试标题"
    assert result["list"][0]["digest"] == "正文内容"
    assert result["list"][0]["nickname"] == "测试号"


def test_build_global_article_cache_creates_standard_parsed_payload():
    service = WechatMPService()

    parsed, html = service._build_global_article_cache({
        "title": "缓存标题",
        "link": "http://mp.weixin.qq.com/s?__biz=abc&mid=123&idx=1&sn=xx#rd",
        "cover": "https://mmbiz.qpic.cn/cover.jpg",
        "content": "<p>缓存正文</p><img data-src=\"https://mmbiz.qpic.cn/a.jpg\" />",
        "nickname": "缓存号",
    })

    assert "js_content" in html
    assert parsed["title"] == "缓存标题"
    assert parsed["author"] == "缓存号"
    assert "缓存正文" in parsed["content_text"]
    assert parsed["article_url"].startswith("http://mp.weixin.qq.com/s")
    assert "https://mmbiz.qpic.cn/cover.jpg" in parsed["images"]
