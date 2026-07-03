# DEVLOG - 开发记录

记录每个阶段的：决策原因 + 踩坑 + 待关注风险点。每阶段不超过 10 行。

### 示例 — 阶段 X：某阶段名称 — 2026-07-03
**决策**
- 为什么选 A 方案而不是 B：一句话原因

**踩坑**
- `某个错误信息` → 原因是 xxx → 解决方法是 yyy

**待关注**
- 目前绕过的一个风险点，后续可能回来修

---

## 阶段 1：项目骨架搭建 — 2026-07-03
**决策**
- Python 标准库自带 sqlite3，不需要额外安装 sqlite-utils 包
- Python 3.14 可用（macOS Homebrew），指定 >=3.11 兼容
- 用 venv 而非全局 pip，macOS 外置管理环境强制要求

**踩坑**
- 直接 `pip3 install` 报 "externally-managed-environment" → 用 `python3 -m venv .venv` 创建虚拟环境解决

**待关注**
- 无

## 阶段 2：核心下载引擎 — 2026-07-03
**决策**
- 用 yt-dlp 内置 `ytsearchN:` 语法做关键词搜索，无需 YouTube API，完全免费
- 画质通过 yt-dlp format string 控制（`bestvideo[height<=720]`），不硬编码分辨率
- 所有下载器功能放在单文件 `downloader.py`，职责清晰：搜索、下载、元信息获取

**踩坑**
- `match_filter_func` 过滤视频时，yt-dlp 跳过下载但仍返回 info dict → 需额外检查文件是否存在判断是否真的下载成功
- 函数名是 `match_filter_func` 不是 `match_filter`，API 文档易误导

**待关注**
- X 和 B站 平台尚未实测下载，后续阶段6单独验证

## 阶段 3：任务管理与持久化 — 2026-07-03
**决策**
- SQLite + WAL 模式，轻量且支持并发读
- URL 唯一约束放在 `(task_id, url)` 上，允许不同任务下载同一视频
- 状态机简单：pending → downloading → completed/failed

**踩坑**
- `add_video` 的 INSERT 和 `get_video` 的 SELECT 用了不同连接 → 新连接看不到未提交的事务 → INSERT 成功但返回 None
  - 修复：同一连接内执行 INSERT + SELECT，然后 commit

**待关注**
- conn.execute 返回的 cursor.lastrowid 在新版本 Python/sqlite3 中行为一致

## 阶段 4：批量下载调度 — 2026-07-03
**决策**
- ThreadPoolExecutor 做并发控制，yt-dlp 是同步的，不需要 asyncio
- 暂停/停止用 threading.Event 信号量，在调度循环中轮询检查
- 失败重试用指数退避（2^1, 2^2, 2^3 秒），最多 3 次
- 调度器实例存在全局 dict 中，支持跨 Streamlit session 启停

**踩坑**
- yt-dlp 进度条输出刷屏 stdout → 后续需要在 downloader 中加 `noprogress: True`
- 调度器的 `run()` 是阻塞调用 → start_task 用 daemon 线程包装，不阻塞 UI

**待关注**
- ThreadPoolExecutor 的 cancel 对已提交的 future 实际无法中断，只能等当前下载完成

## 阶段 5：Web 界面完善 — 2026-07-03
**决策**
- app.py 直接导入所有后端模块（downloader/db/scheduler），不做额外的 API 层，Streamlit 本身就是全栈
- 任务状态通过 SQLite 持久化，页面刷新后直接读 DB 恢复
- 暂停/继续/取消按钮与 scheduler 的 threading.Event 信控对接

**踩坑**
- 无重大踩坑，后端接口设计时已考虑 Streamlit 的 session rerun 模式

**待关注**
- 页面需要手动刷新（按 F5）才能在任务进行中看到最新进度，后续可加 WebSocket 或 auto-refresh

## 阶段 6：打磨与测试 — 待开始
（完成后记录）
