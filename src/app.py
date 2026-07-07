import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from src.db import init_db, create_task, list_tasks, update_task, delete_task, list_task_videos, get_stats, add_video, get_downloaded_urls
from src.scheduler import start_download_only, pause_task, resume_task, cancel_task
from src.downloader import search_videos
from src.x_search import has_x_cookies


st.set_page_config(page_title="Video Crawler", page_icon="▶", layout="wide", initial_sidebar_state="expanded")
init_db()

# ── Session state init ──────────────────────────────────

if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "search_keyword" not in st.session_state:
    st.session_state.search_keyword = ""
if "selected_ids" not in st.session_state:
    st.session_state.selected_ids = set()
if "video_map" not in st.session_state:
    st.session_state.video_map = {}  # {id: {title, url, keyword, platform, duration}}

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

def merge_results(existing: list, new: list) -> list:
    """Merge new results into existing list, dedup by id."""
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
    st.markdown("### ▶ Video Crawler")
    st.divider()

    # ── Search ──
    st.markdown("#### 1. 搜索视频")
    search_kw = st.text_input("关键词", placeholder="输入关键词后点击搜索")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        search_platform = st.selectbox("平台", ["YouTube", "X", "B站"])
    with col_s2:
        search_mode = st.selectbox("模式", ["新搜索", "追加搜索"], help="新搜索=替换结果, 追加=合并到现有结果并去重")

    search_count = st.slider("目标数量", 5, 200, 30, help="最终要显示的视频数")

    # X cookie 状态
    if not has_x_cookies():
        with st.expander("🔑 X/Twitter Cookie 配置", expanded=False):
            st.markdown("""
            **获取 Cookie：**
            1. Chrome/Edge 装 EditThisCookie 扩展
            2. 登录 [x.com](https://x.com) → 导出 → 保存为 `x_cookies.txt`
            3. 放到项目根目录
            **换电脑：** 重复上述步骤
            """)
    else:
        st.success("X Cookie 已配置")

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        min_minutes = st.number_input("最短时长（分钟）", min_value=0, value=0, step=1)
    with col_d2:
        max_minutes = st.number_input("最长时长（分钟）", min_value=0, value=0, step=1, help="0=不限")

    if st.button("🔍 搜索", type="primary", use_container_width=True):
        if not search_kw.strip():
            st.error("请输入关键词")
        elif search_platform == "X" and not has_x_cookies():
            st.error("X 搜索需要 Cookie。请按侧边栏说明配置 x_cookies.txt")
        elif search_platform == "X":
            pass  # X 搜索可用，继续
        else:
            # 多搜一些补偿时长过滤
            fetch_count = search_count * 3 if (min_minutes > 0 or max_minutes > 0) else search_count
            msg = "正在搜索B站（较慢请耐心等待）..." if search_platform in ("B站", "bilibili") else f"正在搜索 {search_kw}..."
            with st.spinner(msg):
                raw_results = search_videos(search_kw, platform=search_platform.lower(), max_results=fetch_count)

            # 时长过滤
            min_sec = min_minutes * 60 if min_minutes > 0 else 0
            max_sec = max_minutes * 60 if max_minutes > 0 else None
            filtered = []
            skipped = 0
            for r in raw_results:
                dur = r.duration or 0
                if min_sec > 0 and dur < min_sec:
                    skipped += 1
                    continue
                if max_sec and dur > max_sec:
                    skipped += 1
                    continue
                filtered.append(r)
                if len(filtered) >= search_count:
                    break

            results = filtered

            if search_mode == "新搜索" or not st.session_state.search_results:
                st.session_state.search_results = results
                st.session_state.search_keyword = search_kw
                st.session_state.selected_ids = set()
                st.session_state.video_map = {}
            else:
                added = merge_results(st.session_state.search_results, results)
                st.info(f"追加 {len(added)} 个新视频（去重后）")

            # 更新 video_map
            for r in st.session_state.search_results:
                st.session_state.video_map[r.id] = {
                    "id": r.id, "title": r.title, "url": r.webpage_url,
                    "keyword": st.session_state.search_keyword or search_kw,
                    "platform": r.platform, "duration": r.duration,
                }

            st.success(f"共 {len(st.session_state.search_results)} 个视频")
            st.rerun()

    st.divider()

    # ── Download settings ──
    st.markdown("#### 2. 下载设置")
    quality = st.selectbox("画质", ["720p", "1080p", "480p", "360p", "最高可用"], index=0)
    concurrency = st.slider("并发数", 1, 10, 3)
    save_path = st.text_input("存储路径", "./data/videos/")

    # ── Download button ──
    sel_count = len(st.session_state.selected_ids)
    btn_label = f"⬇ 下载选中 ({sel_count} 个)" if sel_count else "⬇ 下载选中"
    if st.button(btn_label, type="primary", use_container_width=True, disabled=(sel_count == 0)):
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
                add_video({
                    "task_id": task.id, "keyword": v["keyword"],
                    "video_id": v["id"], "title": v["title"], "url": v["url"],
                    "platform": v["platform"], "duration": v["duration"],
                })
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

st.title("Video Crawler")

tab1, tab2 = st.tabs(["🔍 搜索结果", "📋 任务面板"])

with tab1:
    results = st.session_state.search_results
    if not results:
        st.info("在侧边栏输入关键词并点击「搜索」")
    else:
        sel_ids = st.session_state.selected_ids
        downloaded_urls = get_downloaded_urls()
        already_count = sum(1 for r in results if r.webpage_url in downloaded_urls)
        st.caption(f"搜索 **{st.session_state.search_keyword}** · 共 {len(results)} 个 · 已选 {len(sel_ids)} 个 · 已下载 {already_count} 个")

        # 批量操作按钮
        c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1, 1])
        with c1:
            if st.button("☑ 全选", use_container_width=True):
                st.session_state.selected_ids = {r.id for r in results}
                st.rerun()
        with c2:
            if st.button("☐ 取消", use_container_width=True):
                st.session_state.selected_ids = set()
                st.rerun()
        with c3:
            if st.button("🔄 反选", use_container_width=True):
                all_ids = {r.id for r in results}
                st.session_state.selected_ids = all_ids - st.session_state.selected_ids
                st.rerun()
        with c4:
            if st.button("🆕 未下载", use_container_width=True, help="仅选中未下载过的视频"):
                st.session_state.selected_ids = {
                    r.id for r in results if r.webpage_url not in downloaded_urls
                }
                st.rerun()
        with c6:
            if st.button("🗑 清空", use_container_width=True, help="清空搜索结果"):
                st.session_state.search_results = []
                st.session_state.search_keyword = ""
                st.session_state.selected_ids = set()
                st.session_state.video_map = {}
                st.rerun()

        # ── Video table ──
        for r in results:
            is_sel = r.id in sel_ids
            is_downloaded = r.webpage_url in downloaded_urls
            prefix = "⬇️" if is_downloaded else ""
            title_display = f"{prefix} {r.title[:90]}"

            cols = st.columns([0.5, 5, 1, 0.8])
            with cols[0]:
                # 用按钮代替 checkbox，Streamlit 里更可靠
                btn_key = f"btn_{r.id}"
                if is_sel:
                    if st.button("✅", key=btn_key, help="点击取消选择"):
                        st.session_state.selected_ids.discard(r.id)
                        st.rerun()
                else:
                    if st.button("⬜", key=btn_key, help="点击选择"):
                        st.session_state.selected_ids.add(r.id)
                        st.rerun()
            with cols[1]:
                st.write(f"**{title_display}**")
            with cols[2]:
                st.caption(fmt_duration(r.duration))
            with cols[3]:
                st.caption(r.platform)

        st.divider()
        st.caption("在侧边栏点击「下载选中」开始下载 · 追加搜索可积累更多结果")


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
