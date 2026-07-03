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

## 阶段 3：任务管理与持久化 — 待开始
（完成后记录）

## 阶段 4：批量下载调度 — 待开始
（完成后记录）

## 阶段 5：Web 界面完善 — 待开始
（完成后记录）

## 阶段 6：打磨与测试 — 待开始
（完成后记录）
