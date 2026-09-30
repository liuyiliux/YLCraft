"""实测：X 用户推文列表（UserTweets）。

## 参数来源

twscrape `api.py::user_tweets_raw`：

    op = "SXVCYB8XHSS25nzIljNtZA/UserTweets"
    kv = {
        "userId": str(uid),
        "count": 40,
        "includePromotedContent": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withVoice": True,
        "withV2Timeline": True,
    }

⚠️ 用的是 **userId（数字 id）**，不是 handle。

用法：python backend/_probe_x_user_tweets.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import httpx  # noqa: E402

from app.services.platforms.login_health import (  # noqa: E402
    netscape_to_header,
    resolve_connection,
)
from app.services.platforms.twitter.apis import WEB_BEARER, GQL_URL  # noqa: E402
from app.services.platforms.twitter.xclid import make_transaction_id  # noqa: E402

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)

USER_TWEETS_OP = "SXVCYB8XHSS25nzIljNtZA/UserTweets"


async def main() -> None:
    _cid, raw = resolve_connection("", "TWITTER")
    ck = netscape_to_header(raw, "x.com")
    ckmap = {p.split("=", 1)[0]: p.split("=", 1)[1] for p in ck.split("; ") if "=" in p}
    print(f"  cookie {len(ck)} 字符")

    # 先拿自己的 userId（从 twid）
    import re

    m = re.search(r"twid=u%3D(\d+)", ck)
    uid = m.group(1) if m else ""
    print(f"  自己的 userId = {uid}")

    path = f"/i/api/graphql/{USER_TWEETS_OP}"
    headers = {
        "authorization": f"Bearer {WEB_BEARER}",
        "x-csrf-token": ckmap.get("ct0", ""),
        "cookie": ck,
        "user-agent": UA,
        "x-client-transaction-id": await make_transaction_id(ck, "GET", path),
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "accept": "*/*",
        "referer": "https://x.com/",
    }
    variables = {
        "userId": uid,
        "count": 20,
        "includePromotedContent": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withVoice": True,
        "withV2Timeline": True,
    }
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.get(
            f"{GQL_URL}/{USER_TWEETS_OP}",
            params={"variables": json.dumps(variables)},
            headers=headers,
        )
    print(f"  HTTP {r.status_code}  len={len(r.text)}")
    if not r.text.lstrip().startswith("{"):
        print(f"  非 JSON: {r.text[:150]!r}")
        return

    d = r.json()
    print(f"  顶层键: {list(d.keys())}")
    data = d.get("data") or {}
    print(f"  data 键: {list(data.keys())}")

    # 找 timeline
    user = data.get("user") or {}
    print(f"  user 键: {list(user.keys())}")
    result = user.get("result") or {}
    print(f"  result 键: {list(result.keys())[:14]}")
    tl = result.get("timeline_v2") or result.get("timeline") or {}
    print(f"  timeline 键: {list(tl.keys())}")
    t = tl.get("timeline") or {}
    instr = t.get("instructions") or []
    print(f"  instructions: {len(instr)} 条")
    for ins in instr:
        print(f"    type={ins.get('type')}  键={list(ins.keys())}")
        entries = ins.get("entries") or []
        if entries:
            print(f"      entries={len(entries)}")
            for e in entries[:4]:
                eid = e.get("entryId", "")
                content = e.get("content") or {}
                print(f"        entryId={eid[:50]}  content.type={content.get('entryType')}")

    # 统计推文
    tweets = []
    for ins in instr:
        for e in (ins.get("entries") or []):
            content = e.get("content") or {}
            if content.get("entryType") != "TimelineTimelineItem":
                continue
            item = content.get("itemContent") or {}
            tr = item.get("tweet_results") or {}
            tw = tr.get("result") or {}
            legacy = tw.get("legacy") or {}
            if legacy.get("full_text"):
                tweets.append(legacy)
    print(f"\n  ★ 解析出推文 {len(tweets)} 条")
    for tw in tweets[:3]:
        print(f"    {str(tw.get('full_text'))[:70]!r}")
        print(f"      赞{tw.get('favorite_count')} 转{tw.get('retweet_count')} "
              f"回复{tw.get('reply_count')}  {tw.get('created_at')}")


if __name__ == "__main__":
    asyncio.run(main())
