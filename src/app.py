import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from src.db import init_db, create_task, list_tasks, update_task, delete_task, list_task_videos, get_stats, add_video, get_downloaded_urls, reset_stuck_downloads, reset_stuck_tasks
from src.scheduler import start_download_only, pause_task, resume_task, cancel_task
from src.downloader import search_videos
from src.x_search import has_x_cookies

st.set_page_config(page_title="Video Crawler", page_icon="▶", layout="wide", initial_sidebar_state="expanded")
init_db()
reset_stuck_downloads()
reset_stuck_tasks()

# ── Session state ───────────────────────────────────────

if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "search_keyword" not in st.session_state:
    st.session_state.search_keyword = ""
if "selected_ids" not in st.session_state:
    st.session_state.selected_ids = set()
if "video_map" not in st.session_state:
    st.session_state.video_map = {}

# ── Helpers ─────────────────────────────────────────────

def fmt_size(n_bytes: int | None) -> str:
    if not n_bytes: return "—"
    if n_bytes < 1024: return f"{n_bytes} B"
    if n_bytes < 1024**2: return f"{n_bytes/1024:.1f} KB"
    if n_bytes < 1024**3: return f"{n_bytes/(1024**2):.1f} MB"
    return f"{n_bytes/(1024**3):.1f} GB"

def status_badge(s: str) -> str:
    return {"pending":"⏳ 等待中","running":"● 下载中","paused":"⏸ 已暂停","completed":"✅ 已完成","cancelled":"✕ 已取消"}.get(s, s)

def fmt_duration(sec: float | None) -> str:
    if sec is None: return "—"
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"

def merge_results(existing: list, new: list) -> list:
    seen = {v.id for v in existing}
    added = []
    for v in new:
        if v.id not in seen:
            existing.append(v)
            seen.add(v.id)
            added.append(v)
    return added


# ══════════════════════════════════════════════════════════
#  Sidebar
# ══════════════════════════════════════════════════════════

with st.sidebar:
    # Logo
    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin-bottom:20px'>"
        "<div style='width:36px;height:36px;background:linear-gradient(135deg,#6366f1,#8b5cf6);"
        "border-radius:8px;display:flex;align-items:center;justify-content:center;"
        "color:#fff;font-size:18px'>▶</div>"
        "<span style='font-weight:700;font-size:18px;color:#6366f1'>Video Crawler</span></div>",
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Step 1: Search ──
    st.markdown("#### 1. 搜索视频")
    search_kw = st.text_input("关键词", placeholder="每行一个，或用逗号分隔", label_visibility="collapsed")

    # Platform chips (pills)
    search_platform = st.pills("平台", options=["YouTube", "X", "B站"], default="YouTube", selection_mode="single")

    col_mode, col_clear = st.columns([3, 1])
    with col_mode:
        search_mode = st.selectbox("模式", ["新搜索", "追加搜索"], label_visibility="collapsed", help="新搜索=替换结果, 追加=合并到现有结果并去重")
    with col_clear:
        if st.button("🗑", help="清空搜索结果", width="stretch", key="clear_search"):
            st.session_state.search_results = []
            st.session_state.search_keyword = ""
            st.session_state.selected_ids = set()
            st.session_state.video_map = {}
            st.rerun()

    col_n, col_d1, col_d2 = st.columns([1, 1, 1])
    with col_n:
        search_count = st.selectbox("数量", [5, 10, 20, 30, 50, 100, 200], index=3)
    with col_d1:
        min_minutes = st.number_input("最短(分)", min_value=0, value=0, step=1, help="0=不限")
    with col_d2:
        max_minutes = st.number_input("最长(分)", min_value=0, value=0, step=1, help="0=不限")

    # X cookie 状态
    if not has_x_cookies():
        with st.expander("🔑 X/Twitter Cookie", expanded=False):
            st.markdown("""
            Chrome 装 **EditThisCookie** 扩展 → 登录 [x.com](https://x.com) → 导出 → 保存为 `x_cookies.txt` 放项目根目录
            """)
    else:
        st.caption("X Cookie 已配置")

    if st.button("🔍 搜索", type="primary", width="stretch"):
        if not search_kw.strip():
            st.error("请输入关键词")
        elif search_platform == "X" and not has_x_cookies():
            st.error("X 搜索需要 Cookie")
        else:
            if search_platform == "X":
                fetch_count = search_count
            else:
                fetch_count = search_count * 3 if (min_minutes > 0 or max_minutes > 0) else search_count

            msg = "正在搜索B站（较慢，请耐心等待）..." if search_platform == "B站" else f"正在搜索 {search_kw}..."
            with st.spinner(msg):
                raw_results = search_videos(search_kw, platform=search_platform.lower(), max_results=fetch_count)

            if search_platform == "X":
                filtered = raw_results[:search_count]
            else:
                min_sec = min_minutes * 60 if min_minutes > 0 else 0
                max_sec = max_minutes * 60 if max_minutes > 0 else None
                filtered = []
                for r in raw_results:
                    dur = r.duration or 0
                    if min_sec > 0 and dur < min_sec: continue
                    if max_sec and dur > max_sec: continue
                    filtered.append(r)
                    if len(filtered) >= search_count: break

            if search_mode == "新搜索" or not st.session_state.search_results:
                st.session_state.search_results = filtered
                st.session_state.search_keyword = search_kw
                st.session_state.selected_ids = set()
                st.session_state.video_map = {}
            else:
                added = merge_results(st.session_state.search_results, filtered)
                if added:
                    st.info(f"追加 {len(added)} 个新视频")

            for r in st.session_state.search_results:
                st.session_state.video_map[r.id] = {
                    "id": r.id, "title": r.title, "url": r.webpage_url,
                    "keyword": st.session_state.search_keyword or search_kw,
                    "platform": r.platform, "duration": r.duration,
                }

            st.success(f"共 {len(st.session_state.search_results)} 个视频")
            st.rerun()

    st.divider()

    # ── Step 2: Download ──
    st.markdown("#### 2. 下载设置")

    col_q, col_c = st.columns(2)
    with col_q:
        quality = st.selectbox("画质", ["720p", "1080p", "480p", "360p", "最高可用"], index=0)
    with col_c:
        concurrency = st.selectbox("并发数", [1, 2, 3, 5, 10], index=2)

    save_path = st.text_input("存储路径", value="./data/videos/", label_visibility="collapsed")

    sel_count = len(st.session_state.selected_ids)
    btn_label = f"⬇ 下载选中 ({sel_count} 个)" if sel_count else "⬇ 下载选中"
    if st.button(btn_label, type="primary", width="stretch", disabled=(sel_count == 0)):
        task = create_task({
            "keywords": st.session_state.get("search_keyword", "手动选择"),
            "platforms": search_platform,
            "quality": quality,
            "per_keyword_count": sel_count,
            "concurrency": concurrency,
            "save_path": save_path,
        })
        for vid in st.session_state.selected_ids:
            v = st.session_state.video_map.get(vid)
            if v:
                add_video({"task_id": task.id, "keyword": v["keyword"], "video_id": v["id"], "title": v["title"], "url": v["url"], "platform": v["platform"], "duration": v["duration"]})
        update_task(task.id, total_videos=sel_count)
        start_download_only(task.id)
        st.success(f"任务 {task.id} 已启动 ({sel_count} 个视频)")
        st.session_state.selected_ids = set()
        st.rerun()

    st.divider()
    st.caption(f"已选 {sel_count} 个 · yt-dlp 免费搜索")


# ══════════════════════════════════════════════════════════
#  Main Area
# ══════════════════════════════════════════════════════════

# Header
col_title, col_btn = st.columns([5, 1])
with col_title:
    st.title("任务面板")

# Stats cards
stats = get_stats()
c1, c2, c3 = st.columns(3)
with c1:
    with st.container(border=True):
        st.markdown(f"<div style='color:#6366f1;font-size:22px;font-weight:700'>{stats['total_videos']}</div>", unsafe_allow_html=True)
        st.caption("已下载视频")
with c2:
    with st.container(border=True):
        val = f"{stats['success_rate']}%" if stats["total_videos"] > 0 else "—"
        st.markdown(f"<div style='color:#10b981;font-size:22px;font-weight:700'>{val}</div>", unsafe_allow_html=True)
        st.caption("成功率")
with c3:
    with st.container(border=True):
        st.markdown(f"<div style='color:#f59e0b;font-size:22px;font-weight:700'>{fmt_size(stats['total_size_bytes'])}</div>", unsafe_allow_html=True)
        st.caption("总大小")

# ── Running Tasks ──
all_tasks = sorted(list_tasks(), key=lambda t: t.created_at, reverse=True)
active = [t for t in all_tasks if t.status in ("running","paused","pending")]
past = [t for t in all_tasks if t.status not in ("running","paused","pending")]

st.subheader("运行中", divider=True)

if not active:
    st.info("暂无运行中的任务。在侧边栏创建任务后点击「开始下载」。")

for task in active:
    with st.container(border=True):
        col_head, col_badge = st.columns([3, 1])
        with col_head:
            st.markdown(f"**{task.keywords}**")
        with col_badge:
            badge_color = {"running": "#6366f1", "paused": "#f59e0b", "pending": "#9ca3af"}
            bg = badge_color.get(task.status, "#9ca3af")
            st.markdown(
                f"<span style='display:inline-flex;align-items:center;gap:4px;padding:3px 9px;"
                f"border-radius:20px;font-size:11px;font-weight:600;background:{bg}20;color:{bg}'>"
                f"{status_badge(task.status)}</span>",
                unsafe_allow_html=True,
            )

        st.caption(f"📹 {task.platforms} · 🎯 {task.quality} · 💾 {task.save_path}")

        pct = task.progress_pct
        st.progress(min(pct/100, 1.0), text=f"{task.completed_videos}/{task.total_videos} · {pct:.0f}%")

        cols = st.columns(4)
        with cols[0]:
            if task.status == "running" and st.button("⏸ 暂停", key=f"p_{task.id}", width="stretch"):
                pause_task(task.id); st.rerun()
            if task.status == "paused" and st.button("▶ 继续", key=f"r_{task.id}", width="stretch"):
                resume_task(task.id); st.rerun()
        with cols[1]:
            if st.button("✕ 取消", key=f"c_{task.id}", width="stretch"):
                cancel_task(task.id); st.rerun()
        with cols[2]:
            if st.button("🗑 删除", key=f"d_{task.id}", width="stretch"):
                delete_task(task.id); st.rerun()

# ── Video Table ──
st.subheader("已下载视频", divider=True)

completed_videos = []
for task in past[:5]:
    completed_videos.extend(list_task_videos(task.id, status="completed"))

if not completed_videos:
    st.info("暂无已下载的视频。")
else:
    # Build table data
    rows = []
    for v in completed_videos[-50:]:
        task = [t for t in past if t.id == v.task_id]
        platform = v.platform or "unknown"
        rows.append({
            "文件名": (v.title or v.video_id)[:60],
            "平台": platform,
            "大小": fmt_size(v.file_size),
            "状态": "✅ 完成",
        })

    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "文件名": st.column_config.TextColumn(width="large"),
            "平台": st.column_config.TextColumn(width="small"),
            "大小": st.column_config.TextColumn(width="small"),
            "状态": st.column_config.TextColumn(width="small"),
        },
    )

# ── Auto-refresh ──
if active:
    time.sleep(10)
    st.rerun()
