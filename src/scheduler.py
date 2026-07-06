import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from src.downloader import search_videos, download_video, VideoInfo
from src.db import (
    init_db, get_task, update_task, add_video, update_video,
    list_pending_videos, list_task_videos,
)


MAX_RETRIES = 3


class DownloadScheduler:
    """Manages the lifecycle of a download task."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()
        self._lock = threading.Lock()

    # ── Public API ──────────────────────────────────────

    def run(self, progress_callback: Callable | None = None):
        """
        Full pipeline: search keywords → collect video URLs → download.
        Blocks until done, paused, cancelled, or error.
        """
        task = get_task(self.task_id)
        if task is None:
            return

        update_task(self.task_id, status="running")

        # Phase 1: search and collect videos
        if not self._stop_flag.is_set():
            self._collect_videos(task)

        # Phase 2: download pending videos
        if not self._stop_flag.is_set():
            self._download_pending(task, progress_callback)

        # Final status
        if self._stop_flag.is_set():
            update_task(self.task_id, status="cancelled")
        else:
            self._update_task_stats()

    def pause(self):
        self._pause_flag.set()

    def resume(self):
        self._pause_flag.clear()

    def cancel(self):
        self._stop_flag.set()
        self._pause_flag.clear()

    # ── Internal ────────────────────────────────────────

    def _collect_videos(self, task):
        """Search for each keyword and add videos to DB. Pre-filter by duration."""
        keywords = task.keyword_list
        platforms = task.platform_list
        total = 0
        skipped_duration = 0

        for keyword in keywords:
            if self._stop_flag.is_set():
                return

            for platform in platforms:
                if self._stop_flag.is_set():
                    return

                # 多搜一些，因为有时长过滤会筛掉一部分
                search_count = task.per_keyword_count * 3
                results = search_videos(keyword, platform, search_count)

                for vi in results:
                    if self._stop_flag.is_set():
                        return

                    # 提前按时长过滤，避免下载阶段才发现
                    if task.max_duration and vi.duration:
                        if vi.duration > task.max_duration * 60:
                            skipped_duration += 1
                            continue

                    # 已经够了就停
                    if total >= task.per_keyword_count:
                        break

                    result = add_video({
                        "task_id": task.id,
                        "keyword": keyword,
                        "video_id": vi.id,
                        "title": vi.title,
                        "url": vi.webpage_url,
                        "platform": vi.platform,
                        "duration": vi.duration,
                    })
                    if result is not None:
                        total += 1

                time.sleep(0.5)

        update_task(self.task_id, total_videos=total)

    def _download_pending(self, task, progress_callback=None):
        """Download pending videos with concurrency control."""
        all_pending = list_pending_videos(self.task_id, limit=9999)
        if not all_pending:
            update_task(self.task_id, status="completed")
            return

        concurrency = task.concurrency

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {}
            pending_queue = list(all_pending)
            active_count = 0

            while (pending_queue or active_count > 0) and not self._stop_flag.is_set():
                # Wait if paused
                while self._pause_flag.is_set() and not self._stop_flag.is_set():
                    time.sleep(0.5)

                if self._stop_flag.is_set():
                    break

                # Submit new jobs up to concurrency
                while pending_queue and active_count < concurrency:
                    v = pending_queue.pop(0)
                    update_video(v.id, status="downloading")
                    fut = executor.submit(
                        self._download_one, v, task, progress_callback
                    )
                    futures[fut] = v.id
                    active_count += 1

                # Check completed futures
                done = [f for f in futures if f.done()]
                for f in done:
                    active_count -= 1
                    del futures[f]

                if not done and active_count > 0:
                    time.sleep(0.3)

            # Cleanup remaining futures on cancel
            if self._stop_flag.is_set():
                for f in futures:
                    f.cancel()

    def _download_one(self, video, task, progress_callback=None):
        last_error = "未知错误"
        for attempt in range(1, MAX_RETRIES + 1):
            if self._stop_flag.is_set():
                return

            result = download_video(
                video.url,
                output_dir=task.save_path,
                quality=task.quality,
                max_duration=task.max_duration,
            )

            if "filepath" in result:
                import os
                fp = result["filepath"]
                file_size = os.path.getsize(fp) if os.path.exists(fp) else 0
                update_video(
                    video.id,
                    status="completed",
                    filepath=fp,
                    file_size=file_size,
                )
                if progress_callback:
                    progress_callback(video.id, "completed")
                return

            last_error = result.get("error", "未知错误")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)

        update_video(
            video.id,
            status="failed",
            error_msg=last_error[:300],
        )
        if progress_callback:
            progress_callback(video.id, "failed")

    def _update_task_stats(self):
        """Update task counters after downloads complete."""
        videos = list_task_videos(self.task_id)
        completed = sum(1 for v in videos if v.status == "completed")
        failed = sum(1 for v in videos if v.status == "failed")

        if completed + failed >= len(videos) and len(videos) > 0:
            update_task(
                self.task_id,
                status="completed",
                completed_videos=completed,
                failed_videos=failed,
            )
        else:
            update_task(
                self.task_id,
                status="paused" if self._pause_flag.is_set() else "running",
                completed_videos=completed,
                failed_videos=failed,
            )


# ── Convenience ──────────────────────────────────────────

_active_schedulers: dict[str, DownloadScheduler] = {}


def start_task(task_id: str, progress_callback: Callable | None = None) -> DownloadScheduler:
    """Start a task in a background thread. Returns the scheduler handle."""
    sched = DownloadScheduler(task_id)
    _active_schedulers[task_id] = sched
    thread = threading.Thread(target=sched.run, args=(progress_callback,), daemon=True)
    thread.start()
    return sched


def get_scheduler(task_id: str) -> DownloadScheduler | None:
    return _active_schedulers.get(task_id)


def pause_task(task_id: str):
    sched = _active_schedulers.get(task_id)
    if sched:
        sched.pause()
        update_task(task_id, status="paused")


def resume_task(task_id: str):
    sched = _active_schedulers.get(task_id)
    if sched:
        sched.resume()
        update_task(task_id, status="running")


def cancel_task(task_id: str):
    sched = _active_schedulers.get(task_id)
    if sched:
        sched.cancel()
        update_task(task_id, status="cancelled")
