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
    }

    if max_duration:
        ydl_opts["match_filter"] = yt_dlp.match_filter_func(
            f"duration <= {max_duration * 60}"
        )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return None
            if "entries" in info:
                info = info["entries"][0] if info["entries"] else None
                if info is None:
                    return None

            # Determine actual output filepath
            prepared = ydl.prepare_filename(info)
            if os.path.exists(prepared):
                filepath = prepared
            else:
                # yt-dlp may append extension, try common ones
                base = os.path.splitext(prepared)[0]
                for ext in (".mp4", ".mkv", ".webm"):
                    if os.path.exists(base + ext):
                        filepath = base + ext
                        break
                else:
                    # File doesn't exist — filtered (duration/quality) or failed
                    return None

            return {
                "id": info.get("id", ""),
                "title": info.get("title", ""),
                "filepath": filepath,
                "platform": platform,
            }
    except Exception:
        return None


# ── Search function ──────────────────────────────────────

def search_videos(
    keyword: str,
    platform: str = "youtube",
    max_results: int = 20,
) -> list[VideoInfo]:
    """
    Search videos by keyword on a platform.

    Uses yt-dlp built-in search (free, no API key needed).
    Returns list of VideoInfo.
    """
    search_query = f"ytsearch{max_results}:{keyword}"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "extract_flat": True,
        "noplaylist": True,
        "socket_timeout": 15,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            if info is None or "entries" not in info:
                return []

            results = []
            for entry in info["entries"]:
                if entry is None:
                    continue
                url = entry.get("webpage_url") or entry.get("url", "")
                results.append(VideoInfo(
                    id=entry.get("id", ""),
                    title=entry.get("title", ""),
                    url=url,
                    webpage_url=url,
                    duration=entry.get("duration"),
                    platform=detect_platform(url),
                ))
            return results
    except Exception:
        return []


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
