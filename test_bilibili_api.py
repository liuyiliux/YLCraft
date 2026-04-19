"""测试 B站解析器，模拟实际请求（含额外 URL 参数）"""
import sys, asyncio
sys.path.insert(0, r"F:\PycharmProjects\YLCraft\backend")

import httpx

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _USER_AGENT, "Referer": "https://www.bilibili.com/"}

# 模拟实际传入的完整 URL（含额外 query params）
TEST_URL = (
    "https://www.bilibili.com/video/BV1n3dpBzEQW/"
    "?spm_id_from=333.1007.tianma.1-3-3.click"
    "&vd_source=b9e05b1e056360f9193e01d3dac9325e"
)

def extract_bvid(url: str):
    import re
    patterns = [r"/video/(BV[\w]{10})", r"/video/(bv[\w]{10})"]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

async def test():
    bvid = extract_bvid(TEST_URL)
    print(f"BVID extracted: {bvid}")

    api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    print(f"API URL: {api_url}")

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(api_url, headers=_HEADERS)
        print(f"HTTP status: {resp.status_code}")
        data = resp.json()
        code = data.get("code")
        msg = data.get("message", "")
        d = data.get("data", {})
        print(f"code={code}, message={msg!r}")
        if code == 0:
            print(f"OK title={d.get('title')}")
        else:
            print(f"FAIL Full response: {data}")

asyncio.run(test())
