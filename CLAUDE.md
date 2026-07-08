# CLAUDE.md - 批量视频爬虫

## 项目概述
为大模型多模态评测集批量下载视频。支持 YouTube/X/B站等平台的关键词搜索和批量下载，带 Streamlit 网页操作界面。

## 技术栈
- Python 3.11+
- yt-dlp（核心下载引擎）
- Streamlit（Web UI）
- SQLite（任务状态存储）
- Playwright（X/Twitter 搜索用）

## 项目结构
```
Batch Video Crawler/
├── src/
│   ├── app.py              # Streamlit 入口
│   ├── downloader.py       # yt-dlp 封装
│   ├── scheduler.py        # 批量下载调度
│   ├── db.py               # SQLite 操作
│   └── x_search.py         # X/Twitter 搜索（Playwright+cookie）
├── data/
│   ├── videos/             # 下载的视频文件
│   └── tasks.db            # SQLite 数据库
├── pyproject.toml          # 项目元数据
├── requirements.txt        # Python 依赖
├── spec.md                 # 需求规格
├── todo.md                 # 开发任务
├── DEVLOG.md               # 开发记录（决策原因 + 踩坑）
└── README.md               # 使用说明
```

## 关键约定
- 优先用 yt-dlp 内置搜索（ytsearch），YouTube API 作为可选增强
- 默认并发数 3，避免触发平台限速
- 时长选择：预设选项（5/10/15/30分钟/不限）+ 自定义分钟数输入
- 下载文件命名：`{关键词}_{视频标题}_{视频ID}.mp4`，特殊字符做安全处理
- 去重以 yt-dlp 返回的视频 ID 为准
- 所有配置参数从 Streamlit 侧边栏读取，不硬编码

## 存储估算
- 720p 视频约 5-10MB/分钟
- 100 个 10 分钟视频 ≈ 5-10GB
- 单类别（200 个）≈ 10-20GB

## 平台注意事项
- YouTube：yt-dlp 稳定支持，速率限制宽松。搜索用 ytsearch 语法
- X/Twitter：搜索用 Playwright + EditThisCookie 导出 cookie（x_cookies.txt）。下载用 yt-dlp + Netscape cookie。格式只能用 best，不能设自定义 http_headers（空Referer会403）
- B站：搜索下载都需要自定义 User-Agent 和 Referer header。格式用 best，需完整提取才能拿标题

## 踩坑红线（每次改代码前必读，违反必出bug）

### X/Twitter 平台
- X 下载**禁止设 `http_headers`**（空 Referer 会导致 CDN 返回 403）。只有 B站需要自定义 headers
- X 下载**只能用 `best` 格式**，`bestvideo[height<=720]+bestaudio` 不兼容 X 的 m3u8 格式
- X 搜索返回的 URL 必须是 `https://x.com/{username}/status/{id}`，**禁止 `/i/status/` 格式**
- X 关键词搜索**不存在** yt-dlp extractor，必须用 Playwright + cookie 方案

### B站 平台
- B站搜索**必须设** `extract_flat: False`（完整提取才能拿标题） + 自定义 User-Agent/Referer headers
- B站下载**必须设**自定义 headers（否则 HTTP 412），**只能用 `best` 格式**

### 通用下载
- `download_video` 返回值是 dict（含 `filepath` 或 `error`），不是 None。检查成功用 `"filepath" in result`
- yt-dlp `match_filter_func` 过滤视频后仍返回 info dict，**必须检查文件是否存在**来判断是否真的下载成功
- SQLite 操作中，INSERT 和之后的 SELECT **必须用同一连接**，否则新连接看不到未提交的事务

### Streamlit 开发
- 页面验证**必须打开浏览器确认无红色错误框**，不能只靠 `curl` 判断
- 侧边栏 `st.button` 的 if/elif/else 链中，**不要让某个条件只写 pass 跳过实际逻辑**
- widget key 不能和 `st.session_state` 变量同名，否则 `st.rerun()` 后报 APIException
- 有活跃任务时页面自动 10 秒刷新，避免用户看到过期状态

### 时长过滤
- 时长过滤必须在**搜索/收集阶段**做（`_collect_videos`），多搜 3 倍补偿
- 下载阶段仍有时长过滤作为兜底，但文件不存在 ≠ 下载失败（可能只是被过滤）

### 测试与提交
- **禁止把测试视频文件提交到 git**，测试完后立即删除
- **禁止提交 cookie 文件或数据库文件**

## 开发流程
- 并行任务使用 git worktree 隔离开发，每个独立任务一个 worktree
- 开发完成后合并回主分支，清理 worktree

## 工作流
- 动工前先读 todo.md
- 按 todo.md 顺序执行，不要跳阶段
- 每完成一步子任务：先跑该阶段的"验证"清单 → 确认通过 → 勾选完成 → 再读下一步
- 每完成一个阶段后：更新 DEVLOG.md → 运行 neat-freak 同步文档和记忆 → 推送至github
- 遇到验证不通过的情况：修好再继续，不要跳过验证

### 失败处理与降级
- 同一问题最多重试 3 次，每次尝试不同思路（换方案，不要硬试同一个方法）
- 3 次后仍失败：
  - 该步标记为 ⚠️ 阻塞
  - 先继续做同阶段的下一步（如果有不依赖这步的任务）
  - 如果阻塞了整个阶段，停止并告诉用户：卡在哪、试过什么、建议怎么办
- 降级方案示例：yt-dlp 下载 X 平台失败 3 次 → 临时跳过 X 平台，先完成 YouTube 和 B站，最后单独排查 X
- 不要偷偷替用户做"换技术方案"之类的大决策，阻塞了就沟通
