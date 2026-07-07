"""
X/Twitter 搜索模块。依赖 twikit + cookie 文件。

使用方式:
1. 首次: 在浏览器登录 X → 导出 Netscape 格式 cookie → 存为 x_cookies.txt
2. 程序会自动加载 cookie 进行搜索和下载
3. 换电脑: 重新在新浏览器导出 cookie 并替换文件
"""

import os
import json
import http.cookiejar
from dataclasses import dataclass


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_COOKIE_FILE = os.path.join(PROJECT_ROOT, "x_cookies.txt")
TWIKIT_COOKIE_FILE = os.path.join(PROJECT_ROOT, "x_cookies_twikit.json")


@dataclass
class XVideoResult:
    id: str
    title: str
    url: str
    webpage_url: str
    duration: int | None
    platform: str


def _convert_netscape_to_twikit(netscape_path: str) -> dict | None:
    """将浏览器导出的 Netscape 格式 cookie 转为 twikit 可用的 dict。"""
    try:
        cj = http.cookiejar.MozillaCookieJar(netscape_path)
        cj.load(ignore_discard=True, ignore_expires=True)

        cookies_dict = {}
        for cookie in cj:
            name = cookie.name
            cookies_dict[name] = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": cookie.secure,
            }

        # twikit 需要的核心 cookie
        required = ["auth_token", "ct0"]
        missing = [r for r in required if r not in cookies_dict]
        if missing:
            return None

        # 保存为 twikit 格式
        os.makedirs(os.path.dirname(TWIKIT_COOKIE_FILE), exist_ok=True)
        with open(TWIKIT_COOKIE_FILE, "w") as f:
            json.dump(cookies_dict, f)

        return cookies_dict
    except Exception:
        return None


def has_x_cookies() -> bool:
    """检查是否有可用的 X cookie 文件。"""
    return os.path.exists(DEFAULT_COOKIE_FILE) or os.path.exists(TWIKIT_COOKIE_FILE)


def search_x_videos(keyword: str, max_results: int = 20) -> list[XVideoResult]:
    """使用 cookie 在 X 上搜索视频推文。"""
    try:
        from twikit import Client
    except ImportError:
        return []

    client = Client(language="en-US")

    # 尝试加载 cookie
    if os.path.exists(TWIKIT_COOKIE_FILE):
        client.load_cookies(TWIKIT_COOKIE_FILE)
    elif os.path.exists(DEFAULT_COOKIE_FILE):
        cookies = _convert_netscape_to_twikit(DEFAULT_COOKIE_FILE)
        if cookies is None:
            return []
        client.set_cookies(cookies)
        client.save_cookies(TWIKIT_COOKIE_FILE)
    else:
        return []

    # 搜索视频: 加 filter:media 和 min_faves 减少噪音
    query = f"{keyword} filter:media -filter:retweets"
    results = []

    try:
        import asyncio
        async def _search():
            nonlocal results
            tweets = await client.search_tweet(query, product="Top")
            count = 0
            async for tweet in tweets:
                if tweet.media and hasattr(tweet, "id"):
                    url = f"https://x.com/{tweet.user.screen_name}/status/{tweet.id}"
                    title = (tweet.text or "")[:100].replace("\n", " ")
                    results.append(XVideoResult(
                        id=str(tweet.id),
                        title=title,
                        url=url,
                        webpage_url=url,
                        duration=None,  # X 不返回视频时长
                        platform="x",
                    ))
                    count += 1
                    if count >= max_results:
                        break
            return results

        asyncio.run(_search())
    except Exception:
        pass

    return results
