import sqlite3
import os
import uuid
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone


DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def get_db_path() -> str:
    os.makedirs(DB_DIR, exist_ok=True)
    return os.path.join(DB_DIR, "tasks.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Schema ───────────────────────────────────────────────

def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          TEXT PRIMARY KEY,
                keywords    TEXT NOT NULL,
                platforms   TEXT NOT NULL DEFAULT 'YouTube',
                quality     TEXT NOT NULL DEFAULT '720p',
                max_duration REAL,          -- minutes, NULL = unlimited
                per_keyword_count INTEGER NOT NULL DEFAULT 100,
                concurrency INTEGER NOT NULL DEFAULT 3,
                save_path   TEXT NOT NULL DEFAULT './data/videos',
                status      TEXT NOT NULL DEFAULT 'pending',
                total_videos    INTEGER DEFAULT 0,
                completed_videos INTEGER DEFAULT 0,
                failed_videos   INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS videos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                keyword     TEXT NOT NULL,
                video_id    TEXT NOT NULL,
                title       TEXT NOT NULL,
                url         TEXT NOT NULL,
                platform    TEXT NOT NULL DEFAULT 'unknown',
                duration    REAL,          -- seconds
                status      TEXT NOT NULL DEFAULT 'pending',
                filepath    TEXT,
                file_size   INTEGER,
                error_msg   TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_videos_url
                ON videos(task_id, url);

            CREATE INDEX IF NOT EXISTS idx_videos_task
                ON videos(task_id);

            CREATE INDEX IF NOT EXISTS idx_videos_status
                ON videos(status);
        """)


# ── Task CRUD ────────────────────────────────────────────

@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    keywords: str = ""
    platforms: str = "YouTube"
    quality: str = "720p"
    max_duration: float | None = None
    per_keyword_count: int = 100
    concurrency: int = 3
    save_path: str = "./data/videos"
    status: str = "pending"
    total_videos: int = 0
    completed_videos: int = 0
    failed_videos: int = 0
    created_at: str = ""
    updated_at: str = ""

    @property
    def keyword_list(self) -> list[str]:
        return [k.strip() for k in self.keywords.replace("\n", ",").split(",") if k.strip()]

    @property
    def platform_list(self) -> list[str]:
        return [p.strip() for p in self.platforms.split(",") if p.strip()]

    @property
    def progress_pct(self) -> float:
        if self.total_videos == 0:
            return 0.0
        return (self.completed_videos / self.total_videos) * 100


def create_task(data: dict) -> Task:
    """Create a new task. data keys match Task fields."""
    now = datetime.now(timezone.utc).isoformat()
    task_id = data.get("id", str(uuid.uuid4())[:8])
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO tasks (id, keywords, platforms, quality, max_duration,
               per_keyword_count, concurrency, save_path, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task_id,
                data.get("keywords", ""),
                data.get("platforms", "YouTube"),
                data.get("quality", "720p"),
                data.get("max_duration"),
                data.get("per_keyword_count", 100),
                data.get("concurrency", 3),
                data.get("save_path", "./data/videos"),
                "pending",
                now,
                now,
            ),
        )
    return get_task(task_id)


def get_task(task_id: str) -> Task | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        return None
    return _row_to_task(row)


def list_tasks(status: str | None = None) -> list[Task]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    return [_row_to_task(r) for r in rows]


def update_task(task_id: str, **kwargs) -> Task | None:
    """Update task fields. Only non-None kwargs are updated."""
    if not kwargs:
        return get_task(task_id)
    kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [task_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE tasks SET {sets} WHERE id=?", vals)
    return get_task(task_id)


def delete_task(task_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        keywords=row["keywords"],
        platforms=row["platforms"],
        quality=row["quality"],
        max_duration=row["max_duration"],
        per_keyword_count=row["per_keyword_count"],
        concurrency=row["concurrency"],
        save_path=row["save_path"],
        status=row["status"],
        total_videos=row["total_videos"],
        completed_videos=row["completed_videos"],
        failed_videos=row["failed_videos"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── Video CRUD ───────────────────────────────────────────

@dataclass
class Video:
    id: int = 0
    task_id: str = ""
    keyword: str = ""
    video_id: str = ""
    title: str = ""
    url: str = ""
    platform: str = "unknown"
    duration: float | None = None
    status: str = "pending"
    filepath: str | None = None
    file_size: int | None = None
    error_msg: str | None = None
    created_at: str = ""
    updated_at: str = ""


def add_video(data: dict) -> Video | None:
    """Add a video record. Returns None if URL already exists in this task."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO videos (task_id, keyword, video_id, title, url, platform,
               duration, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                data["task_id"],
                data["keyword"],
                data["video_id"],
                data["title"],
                data["url"],
                data.get("platform", "unknown"),
                data.get("duration"),
                "pending",
                now,
                now,
            ),
        )
        new_id = cur.lastrowid
        conn.commit()
        return _row_to_video(conn.execute("SELECT * FROM videos WHERE id=?", (new_id,)).fetchone())
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_video(pk: int) -> Video | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id=?", (pk,)).fetchone()
    if row is None:
        return None
    return _row_to_video(row)


def list_pending_videos(task_id: str, limit: int = 500) -> list[Video]:
    """Get pending videos for a task (used by scheduler for resume)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE task_id=? AND status='pending' LIMIT ?",
            (task_id, limit),
        ).fetchall()
    return [_row_to_video(r) for r in rows]


def list_task_videos(task_id: str, status: str | None = None) -> list[Video]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM videos WHERE task_id=? AND status=? ORDER BY id",
                (task_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM videos WHERE task_id=? ORDER BY id",
                (task_id,),
            ).fetchall()
    return [_row_to_video(r) for r in rows]


def update_video(pk: int, **kwargs) -> Video | None:
    if not kwargs:
        return get_video(pk)
    kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [pk]
    with get_conn() as conn:
        conn.execute(f"UPDATE videos SET {sets} WHERE id=?", vals)
    return get_video(pk)


def video_exists(task_id: str, url: str) -> bool:
    """Check if a video URL already exists in a task."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM videos WHERE task_id=? AND url=?", (task_id, url)
        ).fetchone()
    return row is not None


def get_downloaded_urls() -> set[str]:
    """Return all video URLs that have been successfully downloaded across all tasks."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT url FROM videos WHERE status='completed'"
        ).fetchall()
    return {r["url"] for r in rows}


def _row_to_video(row: sqlite3.Row) -> Video:
    return Video(
        id=row["id"],
        task_id=row["task_id"],
        keyword=row["keyword"],
        video_id=row["video_id"],
        title=row["title"],
        url=row["url"],
        platform=row["platform"],
        duration=row["duration"],
        status=row["status"],
        filepath=row["filepath"],
        file_size=row["file_size"],
        error_msg=row["error_msg"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── Stats helpers ────────────────────────────────────────

def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as n FROM videos WHERE status='completed'"
        ).fetchone()["n"]
        total_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        total_size = conn.execute(
            "SELECT COALESCE(SUM(file_size), 0) FROM videos WHERE status='completed'"
        ).fetchone()[0]
        success_count = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE status='completed'"
        ).fetchone()[0]
        failed_count = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE status='failed'"
        ).fetchone()[0]
        total_attempts = success_count + failed_count
        success_rate = round(success_count / total_attempts * 100, 1) if total_attempts > 0 else 0

    return {
        "total_videos": total,
        "total_tasks": total_tasks,
        "total_size_bytes": total_size,
        "success_rate": success_rate,
    }


def reset_stuck_downloads() -> int:
    """把卡在'downloading'状态的视频重置为'pending'（调度器崩了后的恢复）。"""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE videos SET status='pending', updated_at=? WHERE status='downloading'",
            (datetime.now(timezone.utc).isoformat(),),
        )
        return cur.rowcount


def reset_stuck_tasks() -> int:
    """把'pending'或'running'状态但没有进行中下载的任务标记为'paused'。"""
    with get_conn() as conn:
        # 找到状态是running/pending但没有downloading中视频的任务
        cur = conn.execute("""
            UPDATE tasks SET status='paused', updated_at=?
            WHERE status IN ('running','pending')
            AND id NOT IN (SELECT DISTINCT task_id FROM videos WHERE status='downloading')
        """, (datetime.now(timezone.utc).isoformat(),))
        return cur.rowcount
