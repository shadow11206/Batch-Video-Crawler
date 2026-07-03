import streamlit as st

st.set_page_config(
    page_title="Video Crawler",
    page_icon="▶",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ──────────────────────────────────────────────

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
    )

    platforms = st.multiselect(
        "平台",
        options=["YouTube", "X", "B站"],
        default=["YouTube"],
    )

    col1, col2 = st.columns(2)
    with col1:
        quality = st.selectbox(
            "画质",
            options=["720p", "1080p", "480p", "360p", "最高可用"],
            index=0,
        )
    with col2:
        duration_preset = st.selectbox(
            "最大时长",
            options=["10 分钟", "5 分钟", "15 分钟", "30 分钟", "自定义", "不限"],
            index=0,
        )
    if duration_preset == "自定义":
        custom_duration = st.number_input(
            "自定义时长（分钟）",
            min_value=1,
            value=10,
            step=1,
            label_visibility="collapsed",
        )

    col3, col4 = st.columns(2)
    with col3:
        per_keyword = st.number_input(
            "每关键词数量",
            min_value=1,
            max_value=500,
            value=100,
        )
    with col4:
        concurrency = st.number_input(
            "并发数",
            min_value=1,
            max_value=10,
            value=3,
        )

    save_path = st.text_input("存储路径", value="./data/videos/")

    st.button("⬇ 开始下载", type="primary", use_container_width=True)

    st.divider()
    st.caption("提示：优先使用 yt-dlp 内置搜索，免费无需 API Key")

# ── Main Area ────────────────────────────────────────────

st.title("任务面板")

# Stats row
c1, c2, c3 = st.columns(3)
with c1:
    with st.container(border=True):
        st.metric("已下载视频", "0")
with c2:
    with st.container(border=True):
        st.metric("成功率", "—")
with c3:
    with st.container(border=True):
        st.metric("总大小", "0 MB")

# Running tasks
st.subheader("运行中", divider=True)
st.info("暂无运行中的任务。在侧边栏创建任务后点击「开始下载」。")

# Completed videos
st.subheader("已下载视频", divider=True)
st.info("暂无已下载的视频。")
