import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import threading
from src.db import init_db, create_task, get_task, list_tasks, update_task, delete_task, list_task_videos, get_stats, add_video
from src.scheduler import start_task, pause_task, resume_task, cancel_task, get_scheduler
from src.downloader import search_videos

st.set_page_config(
    page_title="Video Crawler",
    page_icon="▶",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# ── Session state init ──────────────────────────────────

if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "search_keyword" not in st.session_state:
    st.session_state.search_keyword = ""

# ── Helpers ─────────────────────────────────────────────

def flatten_tasks(tasks):
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

def fmt_duration(sec: float | None) -> str:
    if not sec:
        return "—"
    m, s = divmod(int(sec), 60)
    if m > 0:
        return f"{m}分{s}秒"
    return f"{s}秒"

# ══════════════════════════════════════════════════════════
#  Sidebar
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### ▶ Video Crawler")
    st.caption("大模型多模态评测集批量视频下载工具")
    st.divider()

    # ── 方式一：一键批量下载 ──
    st.markdown("#### 一键批量下载")
    st.caption("输入关键词，自动搜索并下载匹配视频")

    keywords_input = st.text_area(
        "关键词",
        placeholder="每行一个，或用逗号分隔",
        height=70,
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
        duration_preset = st.selectbox("最大时长", options=["10 分钟", "5 分钟", "15 分钟", "30 分钟", "自定义", "不限"], index=0, key="dur1")

    if duration_preset == "自定义":
        max_duration = st.number_input("自定义时长（分钟）", min_value=1, value=10, step=1, key="cd1")
    elif duration_preset == "不限":
        max_duration = None
    else:
        max_duration = int(duration_preset.split()[0])

    c3, c4 = st.columns(2)
    with c3:
        per_keyword = st.number_input("每关键词数量", min_value=1, max_value=500, value=100, key="per_kw")
    with c4:
        concurrency = st.number_input("并发数", min_value=1, max_value=10, value=3, key="cc1")

    save_path = st.text_input("存储路径", value="./data/videos/", key="sp1")

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

    # ── 方式二：先搜索再挑选 ──
    st.markdown("#### 🔍 搜索预览")
    st.caption("先看看有哪些视频，挑好了再下载")

    search_kw = st.text_input(
        "搜索关键词",
        placeholder="输入关键词，点击搜索",
        key="search_kw",
        label_visibility="collapsed",
    )

    sc1, sc2 = st.columns(2)
    with sc1:
        search_platform = st.selectbox("搜索平台", options=["YouTube", "X", "B站"], key="search_plat")
    with sc2:
        search_count = st.number_input("搜索结果数", min_value=5, max_value=50, value=15, step=5, key="search_ct")

    if st.button("🔍 搜索", use_container_width=True, key="search_btn"):
        if not search_kw.strip():
            st.error("请输入搜索关键词")
        else:
            with st.spinner(f"正在搜索 {search_kw} ..."):
                results = search_videos(search_kw, search_platform, search_count)
                st.session_state.search_results = results
                st.session_state.search_keyword = search_kw
                st.session_state.search_platform = search_platform
            st.success(f"找到 {len(results)} 个结果")
            st.rerun()

# ══════════════════════════════════════════════════════════
#  Main Area
# ══════════════════════════════════════════════════════════

# ── 搜索预览结果 ──
if st.session_state.search_results:
    results = st.session_state.search_results
    kw = st.session_state.search_keyword
    plat = st.session_state.get("search_platform", "")

    st.subheader(f"🔍 搜索预览: {kw}", divider=True)
    st.caption(f"平台: {plat} · 共 {len(results)} 个结果 · 勾选后点击下方按钮下载")

    # 全选 / 取消全选
    ca1, ca2 = st.columns([1, 8])
    with ca1:
        if st.button("☑ 全选", key="sel_all"):
            for i in range(len(results)):
                st.session_state[f"sel_{i}"] = True
            st.rerun()
    with ca2:
        pass

    # 视频列表
    selected_videos = []
    for i, vi in enumerate(results):
        key = f"sel_{i}"
        if key not in st.session_state:
            st.session_state[key] = False

        c1, c2, c3 = st.columns([0.5, 6, 1.5])
        with c1:
            checked = st.checkbox("", value=st.session_state[key], key=f"cb_{i}",
                                  on_change=lambda idx=i: st.session_state.__setitem__(f"sel_{idx}", not st.session_state.get(f"sel_{idx}", False)))
            st.session_state[key] = checked
        with c2:
            st.write(f"**{vi.title[:80]}**")
            st.caption(f"{vi.webpage_url[:70]}")
        with c3:
            st.write(f"⏱ {fmt_duration(vi.duration)}")

        if checked:
            selected_videos.append(vi)

    st.divider()

    # 下载选中 + 下载参数
    ccc1, ccc2, ccc3 = st.columns([2, 2, 1])
    with ccc1:
        sel_quality = st.selectbox("画质", options=["720p", "1080p", "480p", "360p", "最高可用"], index=0, key="sq")
    with ccc2:
        sel_dur = st.selectbox("最大时长（二次过滤）", options=["不限", "10 分钟", "5 分钟", "15 分钟", "30 分钟"], index=0, key="sd")
    with ccc3:
        sel_cc = st.number_input("并发", min_value=1, max_value=5, value=2, key="scc")

    sel_path = st.text_input("存储路径", value="./data/videos/", key="ssp")

    if st.button(f"⬇ 下载选中的 {len(selected_videos)} 个视频", type="primary", disabled=len(selected_videos) == 0, key="dl_sel"):
        if not selected_videos:
            st.error("请至少勾选一个视频")
        else:
            # 解析时长限制
            dl_max_dur = None
            if sel_dur != "不限":
                dl_max_dur = int(sel_dur.split()[0])

            # 创建任务
            task = create_task({
                "keywords": f"{kw}(手动挑选)",
                "platforms": plat,
                "quality": sel_quality,
                "max_duration": dl_max_dur,
                "per_keyword_count": len(selected_videos),
                "concurrency": sel_cc,
                "save_path": sel_path,
            })
            # 直接加入挑选的视频，跳过搜索阶段
            for vi in selected_videos:
                add_video({
                    "task_id": task.id,
                    "keyword": kw,
                    "video_id": vi.id,
                    "title": vi.title,
                    "url": vi.webpage_url,
                    "platform": vi.platform,
                    "duration": vi.duration,
                })
            update_task(task.id, total_videos=len(selected_videos))
            start_task(task.id)
            st.session_state.search_results = []
            st.success(f"任务 {task.id} 已启动 · {len(selected_videos)} 个视频")
            st.rerun()

    if st.button("✕ 清空搜索结果", key="clear_search"):
        st.session_state.search_results = []
        st.session_state.search_keyword = ""
        st.rerun()

    st.divider()

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

# ── Active Tasks ──
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

        pct = task.progress_pct
        st.progress(min(pct / 100, 1.0), text=f"{task.completed_videos}/{task.total_videos} · {pct:.0f}%")
        st.caption(f"平台: {task.platforms} · 画质: {task.quality} · 存储: {task.save_path}")

        ctrl1, ctrl2, ctrl3 = st.columns(3)
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
            videos = list_task_videos(task.id, status="completed")
            for v in videos[-5:]:
                col_v1, col_v2 = st.columns([4, 1])
                with col_v1:
                    st.write(f"📹 {v.title[:60]}")
                with col_v2:
                    st.write(fmt_size(v.file_size))

# Auto-refresh
if active_tasks:
    time.sleep(10)
    st.rerun()
