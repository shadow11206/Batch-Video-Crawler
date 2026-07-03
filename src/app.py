import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from src.db import init_db, create_task, get_task, list_tasks, update_task, delete_task, list_task_videos, get_stats
from src.scheduler import start_task, pause_task, resume_task, cancel_task, get_scheduler

st.set_page_config(
    page_title="Video Crawler",
    page_icon="▶",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Init DB ──────────────────────────────────────────────
init_db()

# ── Session helpers ──────────────────────────────────────

def flatten_tasks(tasks):
    """Return tasks sorted by created_at desc."""
    return sorted(tasks, key=lambda t: t.created_at, reverse=True)

def fmt_size(n_bytes: int | None) -> str:
    if not n_bytes:
        return "—"
    if n_bytes < 1024:
        return f"{n_bytes} B"
    if n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.1f} KB"
    if n_bytes < 1024 * 1024 * 1024:
        return f"{n_bytes / (1024**2):.1f} MB"
    return f"{n_bytes / (1024**3):.1f} GB"

def status_badge(status: str) -> str:
    return {
        "pending": "⏳ 等待中",
        "running": "● 下载中",
        "paused": "⏸ 已暂停",
        "completed": "✅ 已完成",
        "cancelled": "✕ 已取消",
    }.get(status, status)

# ══════════════════════════════════════════════════════════
#  Sidebar — New Task
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### ▶ Video Crawler")
    st.caption("大模型多模态评测集批量视频下载工具")
    st.divider()

    st.markdown("#### 新建下载任务")

    keywords_input = st.text_area(
        "关键词",
        placeholder="每行一个，或用逗号分隔\n例如：烹饪教程, 街头采访",
        height=80,
        label_visibility="collapsed",
        key="keywords",
    )

    platforms = st.multiselect(
        "平台",
        options=["YouTube", "X", "B站"],
        default=["YouTube"],
        key="platforms",
    )

    c1, c2 = st.columns(2)
    with c1:
        quality = st.selectbox("画质", options=["720p", "1080p", "480p", "360p", "最高可用"], index=0, key="quality")
    with c2:
        duration_preset = st.selectbox("最大时长", options=["10 分钟", "5 分钟", "15 分钟", "30 分钟", "自定义", "不限"], index=0, key="duration_preset")

    if duration_preset == "自定义":
        custom_duration = st.number_input("自定义时长（分钟）", min_value=1, value=10, step=1, key="custom_dur")
        max_duration = custom_duration
    elif duration_preset == "不限":
        max_duration = None
    else:
        max_duration = int(duration_preset.split()[0])

    c3, c4 = st.columns(2)
    with c3:
        per_keyword = st.number_input("每关键词数量", min_value=1, max_value=500, value=100, key="per_kw")
    with c4:
        concurrency = st.number_input("并发数", min_value=1, max_value=10, value=3, key="concurrency")

    # ── Storage path with folder picker ──
    st.write("存储路径")
    pc1, pc2 = st.columns([4, 1])
    with pc1:
        save_path = st.text_input(
            "存储路径",
            value=st.session_state.get("save_path_val", "./data/videos/"),
            label_visibility="collapsed",
            key="save_path",
        )
        st.session_state["save_path_val"] = save_path
    with pc2:
        show_browser = st.button("📁 选择文件夹", key="browse_btn", use_container_width=True)

    if "show_folder_browser" not in st.session_state:
        st.session_state.show_folder_browser = False
    if show_browser:
        st.session_state.show_folder_browser = not st.session_state.show_folder_browser

    if st.session_state.show_folder_browser:
        current = os.path.abspath(save_path) if save_path else os.path.expanduser("~")
        if not os.path.isdir(current):
            parent = os.path.dirname(current)
            current = parent if os.path.isdir(parent) else os.path.expanduser("~")

        parent_dir = os.path.dirname(current)
        if st.button(f"📂 .. 上级目录", key="folder_parent"):
            st.session_state["save_path_val"] = parent_dir
            st.rerun()

        try:
            entries = sorted(os.listdir(current))
            dirs = [e for e in entries if os.path.isdir(os.path.join(current, e)) and not e.startswith(".")]
        except PermissionError:
            dirs = []

        for d in dirs[:8]:
            full = os.path.join(current, d)
            if st.button(f"📁 {d}", key=f"folder_{d}_{hash(full)}"):
                st.session_state["save_path_val"] = full
                st.rerun()

        if len(dirs) > 8:
            st.caption(f"...还有 {len(dirs) - 8} 个文件夹")
        st.caption(f"当前目录: {current}")

    # ── Create button ──
    if st.button("⬇ 开始下载", type="primary", use_container_width=True, key="start_btn"):
        if not keywords_input.strip():
            st.error("请输入至少一个关键词")
        elif not platforms:
            st.error("请至少选择一个平台")
        else:
            task = create_task({
                "keywords": keywords_input,
                "platforms": ",".join(platforms),
                "quality": quality,
                "max_duration": max_duration,
                "per_keyword_count": per_keyword,
                "concurrency": concurrency,
                "save_path": save_path,
            })
            start_task(task.id)
            st.success(f"任务 {task.id} 已启动")
            st.rerun()

    st.divider()
    st.caption("提示：优先使用 yt-dlp 内置搜索，免费无需 API Key")

# ══════════════════════════════════════════════════════════
#  Main Area — Task Dashboard
# ══════════════════════════════════════════════════════════

st.title("任务面板")

# ── Stats ──
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

# ── Active & Recent Tasks ──
all_tasks = flatten_tasks(list_tasks())
active_tasks = [t for t in all_tasks if t.status in ("running", "paused", "pending")]
past_tasks = [t for t in all_tasks if t.status not in ("running", "paused", "pending")]

st.subheader("运行中", divider=True)

if not active_tasks:
    st.info("暂无运行中的任务。在侧边栏创建任务后点击「开始下载」。")

for task in active_tasks:
    with st.container(border=True):
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.markdown(
                f"**{task.keywords}** &nbsp; "
                f"<span style='font-size:12px;opacity:0.7'>{status_badge(task.status)}</span>",
                unsafe_allow_html=True,
            )
        with col_b:
            st.caption(f"ID: {task.id}")

        # Progress
        pct = task.progress_pct
        st.progress(min(pct / 100, 1.0), text=f"{task.completed_videos}/{task.total_videos} · {pct:.0f}%")
        st.caption(f"平台: {task.platforms} · 画质: {task.quality} · 存储: {task.save_path}")

        # Controls
        ctrl1, ctrl2, ctrl3, ctrl4 = st.columns(4)
        with ctrl1:
            if task.status == "running":
                if st.button("⏸ 暂停", key=f"pause_{task.id}"):
                    pause_task(task.id)
                    st.rerun()
            elif task.status == "paused":
                if st.button("▶ 继续", key=f"resume_{task.id}"):
                    resume_task(task.id)
                    st.rerun()
        with ctrl2:
            if st.button("✕ 取消", key=f"cancel_{task.id}"):
                cancel_task(task.id)
                st.rerun()
        with ctrl3:
            if st.button("🗑 删除", key=f"del_{task.id}"):
                delete_task(task.id)
                st.rerun()

# ── Past Tasks ──
st.subheader("历史任务", divider=True)

if not past_tasks:
    st.info("暂无已完成的任务。")
else:
    for task in past_tasks[:5]:
        with st.container(border=True):
            st.markdown(
                f"**{task.keywords}** &nbsp; "
                f"<span style='font-size:12px;opacity:0.7'>{status_badge(task.status)}</span>"
                f"<span style='font-size:11px;float:right;opacity:0.5'>{task.created_at[:16]}</span>",
                unsafe_allow_html=True,
            )
            st.progress(
                min(task.progress_pct / 100, 1.0),
                text=f"{task.completed_videos}/{task.total_videos} · {task.progress_pct:.0f}%",
            )
            # Show videos for this task
            videos = list_task_videos(task.id, status="completed")
            if videos:
                st.write("")
            for v in videos[-5:]:
                col_v1, col_v2 = st.columns([4, 1])
                with col_v1:
                    st.write(f"📹 {v.title[:60]}")
                with col_v2:
                    st.write(fmt_size(v.file_size))

# ── Auto-refresh for active tasks ──
if active_tasks:
    st.caption("⏳ 自动刷新中...")
    time.sleep(2)
    st.rerun()
