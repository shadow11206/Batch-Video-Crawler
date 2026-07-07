"""
X/Twitter 搜索 — Playwright + 你的浏览器 Cookie + 反检测。

Cookie 文件: x_cookies.txt (EditThisCookie 导出)
首次使用后 cookie 可能过期，重新导出即可。
"""

import json
import os
import time
from dataclasses import dataclass


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIE_FILE = os.path.join(PROJECT_ROOT, "x_cookies.txt")


@dataclass
class XVideoResult:
    id: str
    title: str
    url: str
    webpage_url: str
    duration: int | None
    platform: str


def has_x_cookies() -> bool:
    return os.path.exists(COOKIE_FILE)


def search_x_videos(keyword: str, max_results: int = 20) -> list[XVideoResult]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    if not os.path.exists(COOKIE_FILE):
        return []

    # 加载 cookie
    with open(COOKIE_FILE) as f:
        cookies_raw = json.load(f)

    cookies_pw = [
        {
            "name": c["name"], "value": c["value"],
            "domain": c.get("domain", ".x.com"), "path": c.get("path", "/"),
            "secure": c.get("secure", False), "httpOnly": c.get("httpOnly", False),
        }
        for c in cookies_raw
    ]

    results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
            ),
        )
        context.add_cookies(cookies_pw)

        page = context.new_page()

        # 去掉 webdriver 标记
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            search_url = f"https://x.com/search?q={keyword}&f=video&src=typed_query"
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(5)

            # JS 提取推文（含用户名，用于构造正确URL）
            extract_js = """
            (() => {
                const tweets = [];
                document.querySelectorAll('article').forEach(a => {
                    const links = a.querySelectorAll('a[href*="/status/"]');
                    if (!links.length) return;
                    const href = links[0].getAttribute('href') || '';
                    const m = href.match(/\\/(\\w+)\\/status\\/(\\d+)/);
                    if (!m) return;
                    tweets.push({user: m[1], id: m[2], text: a.innerText.slice(0, 200)});
                });
                return JSON.stringify(tweets);
            })()
            """

            seen_ids = set()
            scrolls = 0

            while len(results) < max_results and scrolls < max_results // 2 + 10:
                raw = page.evaluate(extract_js)
                try:
                    tweets = json.loads(raw)
                    for t in tweets:
                        tid = t.get("id", "")
                        if tid and tid not in seen_ids:
                            seen_ids.add(tid)
                            username = t.get("user", "i")
                            url = f"https://x.com/{username}/status/{tid}"
                            results.append(XVideoResult(
                                id=tid,
                                title=t.get("text", "")[:120].replace("\n", " ") or f"视频 {tid[:8]}",
                                url=url,
                                webpage_url=url,
                                duration=None,
                                platform="x",
                            ))
                except Exception:
                    pass

                if len(results) >= max_results:
                    break

                page.evaluate("window.scrollBy(0, 600)")
                time.sleep(2)
                scrolls += 1

        finally:
            browser.close()

    return results[:max_results]
