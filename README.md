# Batch Video Crawler

大模型多模态评测集批量视频下载工具。输入关键词，自动搜索并批量下载视频，支持 YouTube、X、B站。

![UI Preview](ui-preview.html)

## 功能

- **关键词批量搜索**：输入宽泛类别词，自动搜索匹配视频
- **多平台支持**：YouTube / X (Twitter) / B站 (bilibili)
- **可配置参数**：画质、时长限制、下载数量、并发数
- **断点续传**：中断后重启自动跳过已完成视频
- **网页界面**：Streamlit 侧边栏配置 + 任务面板监控
- **免费搜索**：基于 yt-dlp 内置搜索，无需付费 API

## 快速开始

### 环境要求

- Python 3.11+
- 额外工具：ffmpeg（合并音视频轨）

### 安装

```bash
git clone https://github.com/shadow11206/Batch-Video-Crawler.git
cd Batch-Video-Crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 运行

```bash
source .venv/bin/activate
streamlit run src/app.py
```

浏览器打开 http://localhost:8501

### 使用步骤

1. 左侧输入关键词（每行一个或用逗号分隔）
2. 选择平台、画质、时长等参数
3. 点击「开始下载」
4. 主区域查看进度，可暂停/继续/取消

## 项目结构

```
src/
├── app.py          # Streamlit 入口
├── downloader.py   # yt-dlp 封装（搜索+下载）
├── db.py           # SQLite 数据库操作
└── scheduler.py    # 批量下载调度器
data/
├── videos/         # 下载的视频文件
└── tasks.db        # SQLite 数据库（自动创建）
```

## 下载文件命名

`{关键词}_{视频标题}_{视频ID}.mp4`

## 存储估算

- 720p 视频约 5-10 MB/分钟
- 100 个 × 10 分钟 ≈ 5-10 GB
- 200 个 × 10 分钟 ≈ 10-20 GB

## 平台注意事项

| 平台 | 状态 | 说明 |
|------|------|------|
| YouTube | 稳定 | yt-dlp 完整支持，速率宽松 |
| X | 部分支持 | 视频较短，可能需登录 |
| B站 | 部分支持 | 部分视频需 cookie |

## 技术栈

- Python 3.11+
- yt-dlp（视频下载引擎）
- Streamlit（Web UI）
- SQLite（任务持久化）
