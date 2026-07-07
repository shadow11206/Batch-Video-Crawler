import os
import re
import yt_dlp
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class VideoInfo:
    id: str
    title: str
    url: str
    webpage_url: str
    duration: int | None  # seconds
    platform: str  # "youtube" | "x" | "bilibili" | "unknown"


# ── Quality format strings ───────────────────────────────

QUALITY_FORMATS = {
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "最高可用": "bestvideo+bestaudio/best",
}

# ── Platform detection ───────────────────────────────────

def detect_platform(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "twitter.com" in url or "x.com" in url:
        return "x"
    if "bilibili.com" in url or "b23.tv" in url:
        return "bilibili"
    return "unknown"


# ── Filename sanitization ────────────────────────────────

def safe_filename(name: str, max_len: int = 80) -> str:
    # Remove chars unsafe across platforms
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    # Convert full-width colons and brackets
    name = name.replace("：", "_").replace("；", "_")
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_len:
        name = name[:max_len]
    return name


# ── Download progress hook ───────────────────────────────

def _make_progress_hook(callback: Callable[[dict], None] | None = None):
    def hook(d: dict):
        if callback and d["status"] == "downloading":
            callback(d)
    return hook


# ── Core download function ───────────────────────────────

def download_video(
    url: str,
    output_dir: str = "./data/videos",
    quality: str = "720p",
    max_duration: int | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict | None:
    """
    Download a single video.

    Returns dict with keys: id, title, filepath, platform, or None on failure.
    """
    platform = detect_platform(url)

    # B站用 best 兜底（不兼容 bestvideo/bestaudio 语法）
    if platform == "bilibili":
        fmt = "bestvideo+bestaudio/best"
    else:
        fmt = QUALITY_FORMATS.get(quality, QUALITY_FORMATS["720p"])

    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        "format": fmt,
        "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "progress_hooks": [_make_progress_hook(progress_callback)],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
        "socket_timeout": 30,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/" if platform == "bilibili" else "",
        },
    }

    if max_duration:
        ydl_opts["match_filter"] = yt_dlp.match_filter_func(
            f"duration <= {max_duration * 60}"
        )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return {"error": "yt-dlp 无法获取视频信息"}
            if "entries" in info:
                info = info["entries"][0] if info["entries"] else None
                if info is None:
                    return {"error": "视频列表为空"}

            # Determine actual output filepath
            prepared = ydl.prepare_filename(info)
            if os.path.exists(prepared):
                filepath = prepared
            else:
                base = os.path.splitext(prepared)[0]
                found = False
                for ext in (".mp4", ".mkv", ".webm"):
                    if os.path.exists(base + ext):
                        filepath = base + ext
                        found = True
                        break
                if not found:
                    return {"error": "下载后找不到文件（可能被平台拒绝或需登录）"}

            return {
                "id": info.get("id", ""),
                "title": info.get("title", ""),
                "filepath": filepath,
                "platform": platform,
            }
    except Exception as e:
        return {"error": str(e)[:200]}


# ── Search function ──────────────────────────────────────

def search_videos(
    keyword: str,
    platform: str = "youtube",
    max_results: int = 20,
) -> list[VideoInfo]:
    """
    Search videos by keyword on a supported platform.
    YouTube uses fast flat-extraction. B站 uses full extraction (slower).
    X/Twitter is NOT supported for keyword search — use URL-based download.
    """
    platform = platform.lower()

    if platform == "bilibili" or platform == "b站":
        return _search_bilibili(keyword, max_results)
    elif platform == "x" or platform == "twitter":
        # X/Twitter 没有内置搜索，返回空
        return []
    else:
        return _search_youtube(keyword, max_results)


def _search_youtube(keyword: str, max_results: int) -> list[VideoInfo]:
    """Fast YouTube search via yt-dlp flat extraction."""
    search_query = f"ytsearch{max_results}:{keyword}"
    ydl_opts = {
        "quiet": True, "no_warnings": True, "ignoreerrors": True,
        "extract_flat": True, "noplaylist": True, "socket_timeout": 15,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            if info is None or "entries" not in info:
                return []
            return _parse_results(info, "youtube")
    except Exception:
        return []


def _search_bilibili(keyword: str, max_results: int) -> list[VideoInfo]:
    """B站搜索：需要完整提取才能拿到标题，速度较慢。"""
    search_query = f"bilisearch{max_results}:{keyword}"
    ydl_opts = {
        "quiet": True, "no_warnings": True, "ignoreerrors": True,
        "noplaylist": True, "socket_timeout": 20,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        },
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            if info is None or "entries" not in info:
                return []
            return _parse_results(info, "bilibili")
    except Exception:
        return []


def _parse_results(info: dict, platform: str) -> list[VideoInfo]:
    results = []
    for entry in info.get("entries", []):
        if entry is None:
            continue
        url = entry.get("webpage_url") or entry.get("url", "")
        title = entry.get("title") or ""
        results.append(VideoInfo(
            id=entry.get("id", ""),
            title=title,
            url=url,
            webpage_url=url,
            duration=entry.get("duration"),
            platform=platform,
        ))
    return results


# ── Get video info without downloading ───────────────────

def get_video_info(url: str) -> VideoInfo | None:
    """Fetch metadata without downloading."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "noplaylist": True,
        "socket_timeout": 15,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return None
            return VideoInfo(
                id=info.get("id", ""),
                title=info.get("title", ""),
                url=url,
                webpage_url=info.get("webpage_url", url),
                duration=info.get("duration"),
                platform=detect_platform(url),
            )
    except Exception:
        return None
