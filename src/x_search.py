"""
X/Twitter 搜索 — 通过 Chrome DevTools Protocol 控制你的原生 Chrome。

前提: 运行 enable_chrome_debug.sh 开启 Chrome 调试模式（只需一次）。
之后每次 Chrome 启动都自带调试端口，无需重复操作。
"""

import json
import time
import urllib.request
from dataclasses import dataclass
from threading import Lock

try:
    from websocket import create_connection, WebSocket
except ImportError:
    WebSocket = None

DEBUG_PORT = 9222
CDP_BASE = f"http://localhost:{DEBUG_PORT}"
_wslock = Lock()


@dataclass
class XVideoResult:
    id: str
    title: str
    url: str
    webpage_url: str
    duration: int | None
    platform: str


def has_x_cookies() -> bool:
    """检查 Chrome 调试端口是否可用。"""
    try:
        urllib.request.urlopen(f"{CDP_BASE}/json/version", timeout=2)
        return True
    except Exception:
        return False


def search_x_videos(keyword: str, max_results: int = 20) -> list[XVideoResult]:
    """通过 CDP 控制你的原生 Chrome 搜索 X 视频。"""
    if WebSocket is None:
        print("[X搜索] 请先安装 websocket-client: pip install websocket-client")
        return []

    if not has_x_cookies():
        print("[X搜索] Chrome 调试端口未开启，请运行: bash enable_chrome_debug.sh")
        return []

    try:
        return _cdp_search(keyword, max_results)
    except Exception as e:
        print(f"[X搜索] 搜索异常: {e}")
        return []


def _cdp_search(keyword: str, max_results: int) -> list[XVideoResult]:
    """核心 CDP 搜索逻辑。"""
    results = []

    # 1. 获取或新建 x.com 页面
    tab = _find_or_create_tab("x.com")
    if tab is None:
        return []

    ws_url = tab.get("webSocketDebuggerUrl", "")
    if not ws_url:
        return []

    with _wslock:
        ws = create_connection(ws_url, timeout=10)

    try:
        # 2. 导航到搜索页
        search_url = f"https://x.com/search?q={keyword}&f=video&src=typed_query"
        _cdp_send(ws, "Page.navigate", {"url": search_url})
        time.sleep(5)  # 等 JS 渲染

        # 3. 滚动收集推文
        seen_ids = set()
        scrolls = 0
        max_scrolls = max_results // 2 + 10

        while len(results) < max_results and scrolls < max_scrolls:
            # 用 JS 提取页面中的推文
            script = """
            (() => {
                const tweets = [];
                document.querySelectorAll('article').forEach(a => {
                    const links = a.querySelectorAll('a[href*=\"/status/\"]');
                    if (!links.length) return;
                    const href = links[0].getAttribute('href') || '';
                    const parts = href.split('/status/')[1]?.split('?')[0]?.split('#')[0]?.split('/')[0];
                    if (!parts || !/^\\d+$/.test(parts)) return;
                    tweets.push({id: parts, text: a.innerText?.slice(0, 200) || ''});
                });
                return JSON.stringify(tweets);
            })();
            """

            resp = _cdp_send(ws, "Runtime.evaluate", {
                "expression": script,
                "returnByValue": True,
            })

            try:
                raw = resp.get("result", {}).get("result", {}).get("value", "[]")
                tweets = json.loads(raw) if isinstance(raw, str) else raw
                for t in tweets:
                    tid = t.get("id", "")
                    if tid and tid not in seen_ids:
                        seen_ids.add(tid)
                        results.append(XVideoResult(
                            id=tid,
                            title=t.get("text", "")[:120].replace("\n", " ") or f"视频 {tid[:8]}",
                            url=f"https://x.com/i/status/{tid}",
                            webpage_url=f"https://x.com/i/status/{tid}",
                            duration=None,
                            platform="x",
                        ))
            except Exception:
                pass

            if len(results) >= max_results:
                break

            # 滚动
            _cdp_send(ws, "Runtime.evaluate", {"expression": "window.scrollBy(0, 600)"})
            time.sleep(2)
            scrolls += 1

    finally:
        ws.close()

    return results[:max_results]


def _find_or_create_tab(url_fragment: str) -> dict | None:
    """找到一个已打开的包含 url_fragment 的标签，或新建一个。"""
    try:
        tabs = json.loads(urllib.request.urlopen(f"{CDP_BASE}/json", timeout=5).read())
    except Exception:
        return None

    # 找已有标签
    for t in tabs:
        if t.get("type") == "page" and url_fragment in t.get("url", ""):
            return t

    # 新建标签
    try:
        new = json.loads(urllib.request.urlopen(f"{CDP_BASE}/json/new?url=about:blank", timeout=5).read())
        return new
    except Exception:
        # 返回第一个可用的 page
        pages = [t for t in tabs if t.get("type") == "page"]
        return pages[0] if pages else None


def _cdp_send(ws, method: str, params: dict | None = None) -> dict:
    """发送 CDP 命令并等待响应。"""
    msg_id = int(time.time() * 1000) % 100000
    msg = json.dumps({"id": msg_id, "method": method, "params": params or {}})
    ws.send(msg)

    # 收响应
    while True:
        resp = json.loads(ws.recv())
        if resp.get("id") == msg_id:
            return resp
        # 忽略异步事件
