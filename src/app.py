import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from src.db import init_db, create_task, list_tasks, update_task, delete_task, list_task_videos, get_stats, add_video
from src.scheduler import start_task, start_download_only, pause_task, resume_task, cancel_task
from src.downloader import search_videos


st.set_page_config(page_title="Video Crawler", page_icon="▶", layout="wide", initial_sidebar_state="expanded")
init_db()

# ── Session state init ──────────────────────────────────

if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "search_keyword" not in st.session_state:
    st.session_state.search_keyword = ""

# ── Helpers ─────────────────────────────────────────────

def fmt_size(n_bytes: int | None) -> str:
    if not n_bytes: return "—"
    if n_bytes < 1024: return f"{n_bytes} B"
    if n_bytes < 1024**2: return f"{n_bytes/1024:.1f} KB"
    if n_bytes < 1024**3: return f"{n_bytes/(1024**2):.1f} MB"
    return f"{n_bytes/(1024**3):.1f} GB"

def status_badge(s: str) -> str:
    return {"pending":"⏳","running":"●","paused":"⏸","completed":"✅","cancelled":"✕"}.get(s, s)

def fmt_duration(sec: float | None) -> str:
    if sec is None: return "—"
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


# ══════════════════════════════════════════════════════════
#  Sidebar
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### ▶ Video Crawler")
    st.divider()

    # ── Step 1: Search ──
    st.markdown("#### 1. 搜索视频")
    search_kw = st.text_input("关键词", placeholder="输入关键词后点击搜索", key="search_input")
    search_platform = st.selectbox("平台", ["YouTube", "X", "B站"], key="search_platform")
    search_count = st.slider("搜索数量", 5, 50, 20, key="search_count")

    if st.button("🔍 搜索", type="primary", use_container_width=True):
        if not search_kw.strip():
            st.error("请输入关键词")
        else:
            with st.spinner(f"正在搜索 {search_kw}..."):
                results = search_videos(search_kw, platform=search_platform.lower(), max_results=search_count)
                st.session_state.search_results = results
                st.session_state.search_keyword = search_kw
            st.success(f"找到 {len(results)} 个视频")
            st.rerun()

    st.divider()

    # ── Step 2: Download settings ──
    st.markdown("#### 2. 下载设置")
    quality = st.selectbox("画质", ["720p", "1080p", "480p", "360p", "最高可用"], index=0, key="dl_quality")
    duration_preset = st.selectbox("最大时长", ["10 分钟","5 分钟","15 分钟","30 分钟","自定义","不限"], index=0, key="dl_dur")
    if duration_preset == "自定义":
        max_duration = st.number_input("自定义（分钟）", min_value=1, value=10, step=1)
    elif duration_preset == "不限":
        max_duration = None
    else:
        max_duration = int(duration_preset.split()[0])

    concurrency = st.slider("并发数", 1, 10, 3, key="dl_conc")
    save_path = st.text_input("存储路径", "./data/videos/", key="dl_path")

    # ── Download button ──
    selected_count = len(st.session_state.get("selected_videos", []))
    btn_label = f"⬇ 下载选中 ({selected_count} 个)" if selected_count else "⬇ 下载选中"
    if st.button(btn_label, type="primary", use_container_width=True, disabled=(selected_count == 0)):
        selected = st.session_state.selected_videos
        task = create_task({
            "keywords": st.session_state.get("search_keyword", "手动选择"),
            "platforms": search_platform,
            "quality": quality,
            "max_duration": max_duration,
            "per_keyword_count": len(selected),
            "concurrency": concurrency,
            "save_path": save_path,
        })
        for v in selected:
            add_video({
                "task_id": task.id, "keyword": v["keyword"],
                "video_id": v["id"], "title": v["title"], "url": v["url"],
                "platform": v["platform"], "duration": v["duration"],
            })
        update_task(task.id, total_videos=len(selected))
        start_download_only(task.id)
        st.session_state.selected_videos = []
        st.session_state.search_results = []
        st.success(f"任务 {task.id} 已启动 ({len(selected)} 个视频)")
        st.rerun()

    st.divider()
    st.caption("提示：使用 yt-dlp 内置搜索，免费无需 API Key")


# ══════════════════════════════════════════════════════════
#  Main Area
# ══════════════════════════════════════════════════════════

st.title("Video Crawler")

# ── Tab 1: Search Results ──────────────────────────────

tab1, tab2 = st.tabs(["🔍 搜索结果", "📋 任务面板"])

with tab1:
    results = st.session_state.search_results
    if not results:
        st.info("在侧边栏输入关键词并点击「搜索」")
    else:
        st.caption(f"搜索 **{st.session_state.search_keyword}** · 共 {len(results)} 个视频")

        # Build selection UI
        if "selected_videos" not in st.session_state:
            st.session_state.selected_videos = []

        selected_ids = {v["id"] for v in st.session_state.selected_videos}

        # Select all / deselect all
        c_all, c_sel, _ = st.columns([1, 1, 4])
        with c_all:
            if st.button("全选", key="select_all"):
                st.session_state.selected_videos = [
                    {"id": r.id, "title": r.title, "url": r.webpage_url,
                     "keyword": st.session_state.search_keyword,
                     "platform": r.platform, "duration": r.duration}
                    for r in results
                ]
                st.rerun()
        with c_sel:
            if st.button("取消全选", key="deselect_all"):
                st.session_state.selected_videos = []
                st.rerun()

        # Video table with inline checkboxes
        for i, r in enumerate(results):
            cols = st.columns([0.5, 5, 1, 1])
            with cols[0]:
                checked = r.id in selected_ids
                if st.checkbox("", value=checked, key=f"chk_{i}_{r.id}", label_visibility="collapsed"):
                    if r.id not in selected_ids:
                        st.session_state.selected_videos.append({
                            "id": r.id, "title": r.title, "url": r.webpage_url,
                            "keyword": st.session_state.search_keyword,
                            "platform": r.platform, "duration": r.duration,
                        })
                else:
                    st.session_state.selected_videos = [
                        v for v in st.session_state.selected_videos if v["id"] != r.id
                    ]
            with cols[1]:
                st.write(f"**{r.title[:80]}**")
            with cols[2]:
                st.caption(fmt_duration(r.duration))
            with cols[3]:
                st.caption(r.platform)

        st.divider()
        st.caption(f"已选 {len(st.session_state.selected_videos)} 个 · 在侧边栏点击「下载选中」开始下载")

# ── Tab 2: Task Dashboard ──────────────────────────────

with tab2:
    stats = get_stats()
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.metric("已下载视频", stats["total_videos"])
    with c2:
        with st.container(border=True):
            st.metric("成功率", f"{stats['success_rate']}%" if stats["total_videos"] > 0 else "—")
    with c3:
        with st.container(border=True):
            st.metric("总大小", fmt_size(stats["total_size_bytes"]))

    all_tasks = sorted(list_tasks(), key=lambda t: t.created_at, reverse=True)
    active = [t for t in all_tasks if t.status in ("running","paused","pending")]
    past = [t for t in all_tasks if t.status not in ("running","paused","pending")]

    st.subheader("运行中", divider=True)
    if not active:
        st.info("暂无运行中的任务")
    for task in active:
        with st.container(border=True):
            st.markdown(f"**{task.keywords}** &nbsp; *{status_badge(task.status)}*")
            pct = task.progress_pct
            st.progress(min(pct/100, 1.0), text=f"{task.completed_videos}/{task.total_videos} · {pct:.0f}%")
            st.caption(f"平台:{task.platforms} · 画质:{task.quality} · {task.save_path}")
            cb1, cb2, _ = st.columns([1,1,4])
            with cb1:
                if task.status == "running" and st.button("⏸ 暂停", key=f"p_{task.id}"):
                    pause_task(task.id); st.rerun()
                if task.status == "paused" and st.button("▶ 继续", key=f"r_{task.id}"):
                    resume_task(task.id); st.rerun()
            with cb2:
                if st.button("✕ 取消", key=f"c_{task.id}"):
                    cancel_task(task.id); st.rerun()

    st.subheader("历史任务", divider=True)
    if not past:
        st.info("暂无已完成的任务")
    else:
        for task in past[:5]:
            with st.container(border=True):
                st.markdown(f"**{task.keywords}** &nbsp; *{status_badge(task.status)}* · {task.created_at[:16]}")
                st.progress(min(task.progress_pct/100, 1.0), text=f"{task.completed_videos}/{task.total_videos}")
                videos = list_task_videos(task.id, status="completed")
                for v in videos[-5:]:
                    st.write(f"📹 {v.title[:60]} · {fmt_size(v.file_size)}")

# ── Auto-refresh ──
if active:
    time.sleep(10)
    st.rerun()
