#!/bin/bash
# 快速启动歌词追踪器

# 检查是否安装了playerctl
if ! command -v playerctl &> /dev/null; then
    echo "错误: 未找到 playerctl，请先安装："
    echo "  Arch Linux: sudo pacman -S playerctl"
    echo "  Ubuntu/Debian: sudo apt-get install playerctl"
    echo "  Fedora: sudo dnf install playerctl"
    exit 1
fi

# 检查是否安装了Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3"
    exit 1
fi

# 检查是否安装了依赖
if ! python3 -c "import requests; import tomllib" &> /dev/null && ! python3 -c "import requests; import tomli" &> /dev/null; then
    echo "正在安装依赖..."
    pip3 install -r requirements.txt
fi

# 运行脚本
python3 lyric_tracker.py
