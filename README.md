# 实时歌词追踪器

一个使用 Python 编写的实时歌词追踪工具，通过 `playerctl` 获取当前播放的音乐信息，并从网易云音乐 API 获取歌词和翻译，在终端实时显示。
##我博客
[Linux歌词同步工具 - Zeyao Dev](https://www.zeyao.top/post.php?id=6979afb8158c4)
## 功能特点

- 自动检测当前播放的音乐
- 自动搜索网易云音乐ID
- 实时显示歌词和翻译
- 精确的歌词时间同步
- 终端进度条显示（基于 `mpris:length` + `playerctl position`）
- 支持 `config.toml` 配置颜色/进度条/刷新频率等

## 依赖要求

- Python 3.7+
- `playerctl` (用于获取播放器信息)
- `requests` Python库
- Python 3.11+ 使用内置 `tomllib`；Python <=3.10 需要 `tomli`

## 安装

1. 安装 `playerctl`:
   ```bash
   # Arch Linux
   sudo pacman -S playerctl
   
   # Ubuntu/Debian
   sudo apt-get install playerctl
   
   # Fedora
   sudo dnf install playerctl
   ```

2. 安装 Python 依赖:
   ```bash
   pip install -r requirements.txt
   ```

3. 确保脚本有执行权限:
   ```bash
   chmod +x lyric_tracker.py
   ```

## 使用方法

1. 确保你的音乐播放器正在运行（支持 MPRIS 的播放器，如 Spotify、VLC、Rhythmbox 等）

2. 运行脚本:
   ```bash
   python lyric_tracker.py
   ```
   或
   ```bash
   ./lyric_tracker.py
   ```

3. 脚本会自动：
   - 检测当前播放的歌曲
   - 搜索对应的网易云音乐ID
   - 获取歌词和翻译
   - 根据播放进度实时显示歌词

## 配置（TOML）

默认读取脚本同目录的 `config.toml`。也可以用环境变量指定：

```bash
export LYRIC_TRACKER_CONFIG=/path/to/config.toml
```

常用配置项：

- `colors.*`: 控制各区域颜色（可写颜色名如 `bright_cyan`，或直接写 SGR 如 `1;36`）
- `ui.progress_bar_length`: 进度条长度
- `loop.poll_interval`/`loop.render_interval`: 轮询/渲染频率

## 工作原理

1. **音乐检测**: 使用 `playerctl` 命令获取当前播放的音乐标题和艺术家
2. **ID搜索**: 通过网易云音乐搜索API查找歌曲ID
3. **歌词获取**: 使用提供的API获取LRC格式的歌词和翻译
4. **时间同步**: 解析LRC时间戳，根据 `playerctl position` 返回的播放位置匹配对应歌词
5. **实时显示**: 在终端中实时更新显示当前歌词和下一句歌词

## 注意事项

- 需要网络连接以搜索歌曲和获取歌词
- 播放器必须支持 MPRIS 协议（大多数现代Linux音乐播放器都支持）
- 如果歌曲在网易云音乐中不存在，将无法显示歌词
- 歌词同步精度取决于API返回的时间戳质量

## 故障排除

如果遇到问题：

1. **无法检测到音乐**: 确保播放器正在播放，并且支持 MPRIS
   ```bash
   playerctl status
   ```

2. **找不到歌曲**: 歌曲可能在网易云音乐中不存在，或者搜索关键词不匹配

3. **歌词不同步**: 可能是API返回的时间戳不准确，或者播放器位置信息有延迟

