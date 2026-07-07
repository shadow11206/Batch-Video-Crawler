# Batch Video Crawler

大模型多模态评测集批量视频下载工具。输入关键词 → 预览视频列表 → 勾选下载，支持 YouTube、X、B站。

## 功能

- **搜索预览**：先搜索看结果，勾选想要的再下载，不是一键盲下
- **追加搜索**：同关键词可反复搜索积累更多结果，自动去重
- **多平台支持**：YouTube / X (Twitter) / B站 (bilibili)
- **可配置参数**：画质、时长范围、搜索数量、并发数
- **断点续传**：中断后重启自动跳过已完成视频
- **跨任务去重**：已下载过的视频在搜索结果中标记 ⬇️
- **网页界面**：Streamlit 侧边栏 + 主区域 Tab 切换

## 快速开始

### 环境要求

- Python 3.11+
- ffmpeg（合并音视频轨）
- Chromium 浏览器（Playwright 自动安装）

### 安装

```bash
git clone https://github.com/shadow11206/Batch-Video-Crawler.git
cd Batch-Video-Crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### X/Twitter 配置（仅 X 平台需要）

1. Chrome/Edge 安装 **EditThisCookie** 扩展
2. 打开 [x.com](https://x.com) 并登录
3. 点击扩展 → 导出 → 保存为 `x_cookies.txt` 放到项目根目录
4. 换电脑：在新电脑浏览器重复上述步骤

YouTube 和 B站无需任何配置。

### 运行

```bash
source .venv/bin/activate
streamlit run src/app.py
```

浏览器打开 http://localhost:8501

### 使用步骤

1. 侧边栏 **"1. 搜索视频"** — 输入关键词，选平台，点搜索
2. 主区域 **"搜索结果"** Tab — 勾选想要的视频（支持全选/反选/仅未下载）
3. 侧边栏 **"2. 下载设置"** — 选画质、并发数、路径 → 点下载选中
4. **"任务面板"** Tab — 查看进度，可暂停/取消

## 项目结构

```
src/
├── app.py          # Streamlit 入口
├── downloader.py   # yt-dlp 封装（搜索+下载）
├── db.py           # SQLite 数据库操作
├── scheduler.py    # 批量下载调度器
└── x_search.py     # X/Twitter Playwright 搜索
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

## 平台详情

| 平台 | 搜索 | 下载 | 配置 | 成功率 |
|------|:--:|:--:|------|:--:|
| YouTube | 快速（flat 模式） | ✅ | 无 | 90%+ |
| B站 | 稍慢（完整提取） | ✅ | 无 | 80%+ |
| X | Playwright + Cookie | ✅ | x_cookies.txt | 50%+（GIF/嵌入视频无法下载） |

## 技术栈

- Python 3.11+
- yt-dlp（视频下载引擎）
- Streamlit（Web UI）
- Playwright（X/Twitter 搜索）
- SQLite（任务持久化）
