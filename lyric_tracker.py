#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时歌词追踪脚本
使用 playerctl 获取播放信息，通过网易云API获取歌词并实时显示
"""

import requests
import json
import subprocess
import re
import time
import sys
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python <=3.10
    import tomli as tomllib


@dataclass
class LyricLine:
    """歌词行数据类"""
    time: float  # 时间戳（秒）
    text: str    # 歌词文本


@dataclass
class SongInfo:
    """歌曲信息"""
    title: str
    artist: str
    netease_id: Optional[int] = None


@dataclass
class AppConfig:
    config_path: str

    # loop
    poll_interval: float = 0.10
    render_interval: float = 0.10

    # ui
    width: int = 80
    progress_bar_length: int = 50
    progress_filled: str = "█"
    progress_empty: str = "░"
    show_next: bool = True

    # colors (names or raw SGR like "1;36")
    colors: Dict[str, str] = None

    def __post_init__(self):
        if self.colors is None:
            self.colors = {
                "header_border": "bright_magenta",
                "song_info": "bright_green",
                "time": "cyan",
                "section_title": "bright_yellow",
                "current_lyric": "bright_cyan",
                "current_trans": "bright_black",
                "next_lyric": "white",
                "next_trans": "bright_black",
                "dim": "bright_black",
            }


ANSI_COLOR_MAP = {
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
    "bright_black": "90",
    "bright_red": "91",
    "bright_green": "92",
    "bright_yellow": "93",
    "bright_blue": "94",
    "bright_magenta": "95",
    "bright_cyan": "96",
    "bright_white": "97",
}


def sgr(name_or_code: str) -> str:
    """颜色名/SGR码 -> ANSI escape（不含 reset）"""
    if not name_or_code:
        return ""
    code = ANSI_COLOR_MAP.get(name_or_code, name_or_code)
    return f"\033[{code}m"


def ansi_wrap(text: str, color: Optional[str]) -> str:
    if text is None:
        return ""
    if not color:
        return text
    return f"{sgr(color)}{text}\033[0m"


def load_config(path: Optional[str] = None) -> AppConfig:
    # 优先：环境变量；其次：脚本同目录 config.toml
    config_path = path or os.environ.get("LYRIC_TRACKER_CONFIG") or str(Path(__file__).with_name("config.toml"))
    cfg = AppConfig(config_path=config_path)

    p = Path(config_path)
    if not p.exists():
        return cfg

    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"读取配置失败: {e}（将使用默认配置）", file=sys.stderr)
        return cfg

    colors = data.get("colors") or {}
    ui = data.get("ui") or {}
    loop = data.get("loop") or {}

    if isinstance(colors, dict):
        for k, v in colors.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                cfg.colors[k] = v.strip()

    if isinstance(ui, dict):
        if isinstance(ui.get("width"), int):
            cfg.width = max(40, ui["width"])
        if isinstance(ui.get("progress_bar_length"), int):
            cfg.progress_bar_length = max(10, ui["progress_bar_length"])
        if isinstance(ui.get("progress_filled"), str) and ui["progress_filled"]:
            cfg.progress_filled = ui["progress_filled"]
        if isinstance(ui.get("progress_empty"), str) and ui["progress_empty"]:
            cfg.progress_empty = ui["progress_empty"]
        if isinstance(ui.get("show_next"), bool):
            cfg.show_next = ui["show_next"]

    if isinstance(loop, dict):
        if isinstance(loop.get("poll_interval"), (int, float)):
            cfg.poll_interval = max(0.02, float(loop["poll_interval"]))
        if isinstance(loop.get("render_interval"), (int, float)):
            cfg.render_interval = max(0.02, float(loop["render_interval"]))

    return cfg


class NeteaseMusicSearcher:
    """网易云音乐搜索器"""
    
    @staticmethod
    def search_song(song_name: str, artist: str = "") -> Optional[int]:
        """
        搜索网易云音乐并获取歌曲ID
        
        参数:
            song_name: 歌曲名称
            artist: 艺术家名称（可选）
        
        返回:
            歌曲ID，如果未找到返回None
        """
        # 构建搜索关键词
        search_keyword = f"{song_name} {artist}".strip()
        
        url = "https://music.163.com/api/search/get/web"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://music.163.com/'
        }
        
        params = {
            's': search_keyword,
            'type': 1,  # 单曲
            'offset': 0,
            'limit': 10
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == 200 and 'result' in data and 'songs' in data['result']:
                songs = data['result']['songs']
                
                if not songs:
                    return None
                
                # 尝试精确匹配
                song_name_lower = song_name.lower()
                artist_lower = artist.lower() if artist else ""
                
                for song in songs:
                    song_title = song['name'].lower()
                    song_artists = [a['name'].lower() for a in song['artists']]
                    
                    # 检查标题匹配
                    if song_name_lower in song_title or song_title in song_name_lower:
                        # 如果提供了艺术家，检查是否匹配
                        if not artist_lower or any(artist_lower in a or a in artist_lower for a in song_artists):
                            return song['id']
                
                # 如果没有精确匹配，返回第一个结果
                return songs[0]['id']
            
            return None
            
        except Exception as e:
            print(f"搜索歌曲时出错: {e}", file=sys.stderr)
            return None


class LyricParser:
    """歌词解析器"""
    
    @staticmethod
    def parse_lrc(lrc_text: str) -> List[LyricLine]:
        """
        解析LRC格式歌词
        
        参数:
            lrc_text: LRC格式的歌词文本
        
        返回:
            歌词行列表，按时间排序
        """
        lyrics = []
        
        # 匹配时间戳和歌词的正则表达式
        # 格式: [mm:ss.xx] 或 [mm:ss.xxx] 或 [mm:ss]
        # 支持一行多个时间戳的情况
        time_pattern = r'\[(\d{2}):(\d{2})(?:\.(\d{2,3}))?\]'
        
        for line in lrc_text.strip().split('\n'):
            # 找到所有时间戳
            time_matches = list(re.finditer(time_pattern, line))
            
            if time_matches:
                # 提取歌词文本（最后一个时间戳之后的内容）
                last_match_end = time_matches[-1].end()
                text = line[last_match_end:].strip()
                
                # 为每个时间戳创建一条歌词记录
                for match in time_matches:
                    minutes, seconds, milliseconds = match.groups()
                    time_seconds = int(minutes) * 60 + int(seconds)
                    
                    if milliseconds:
                        # 处理毫秒（可能是2位或3位）
                        if len(milliseconds) == 2:
                            time_seconds += int(milliseconds) / 100.0
                        else:
                            time_seconds += int(milliseconds) / 1000.0
                    
                    if text:  # 只添加非空歌词
                        lyrics.append(LyricLine(time=time_seconds, text=text))
        
        # 按时间排序并去重（相同时间的歌词只保留一条）
        lyrics.sort(key=lambda x: x.time)
        
        # 去重：相同时间的歌词只保留最后一条（通常是更完整的版本）
        unique_lyrics = []
        seen_times = set()
        for lyric in reversed(lyrics):
            # 使用四舍五入到0.01秒的时间作为键，避免浮点精度问题
            time_key = round(lyric.time, 2)
            if time_key not in seen_times:
                seen_times.add(time_key)
                unique_lyrics.append(lyric)
        
        # 再次排序（因为reversed了）
        unique_lyrics.sort(key=lambda x: x.time)
        
        return unique_lyrics
    
    @staticmethod
    def get_current_lyric(lyrics: List[LyricLine], current_time: float) -> Tuple[Optional[str], Optional[str]]:
        """
        根据当前时间获取对应的歌词（优化的对轨算法）
        
        参数:
            lyrics: 歌词列表
            current_time: 当前播放时间（秒）
        
        返回:
            (当前歌词, 下一句歌词) 的元组
        """
        if not lyrics:
            return None, None
        
        # 使用二分查找优化性能（虽然列表不大，但更优雅）
        # 找到最后一个时间 <= current_time 的歌词
        current_lyric = None
        next_lyric = None
        
        # 从后往前查找，找到最后一个时间戳小于等于当前时间的歌词
        for i in range(len(lyrics) - 1, -1, -1):
            if lyrics[i].time <= current_time:
                current_lyric = lyrics[i].text
                # 获取下一句歌词
                if i + 1 < len(lyrics):
                    next_lyric = lyrics[i + 1].text
                break
        
        # 如果没找到，说明还没开始，返回第一句作为预览
        if current_lyric is None and lyrics:
            next_lyric = lyrics[0].text
        
        return current_lyric, next_lyric


class PlayerctlMonitor:
    """Playerctl 监控器"""
    
    @staticmethod
    def get_metadata() -> Optional[SongInfo]:
        """
        获取当前播放的音乐信息
        
        返回:
            SongInfo对象，如果获取失败返回None
        """
        # 尝试第一种方式
        try:
            result = subprocess.run(
                ['playerctl', 'metadata', '--format', '{{ artist }}|{{ title }}'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split('|', 1)
                if len(parts) == 2:
                    artist, title = parts
                    return SongInfo(title=title.strip(), artist=artist.strip())
        except:
            pass
        
        # 尝试第二种方式：分别获取
        try:
            title_result = subprocess.run(
                ['playerctl', 'metadata', 'title'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            artist_result = subprocess.run(
                ['playerctl', 'metadata', 'artist'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if title_result.returncode == 0:
                title = title_result.stdout.strip()
                artist = artist_result.stdout.strip() if artist_result.returncode == 0 else ""
                if title:
                    return SongInfo(title=title, artist=artist)
        except:
            pass
        
        return None
    
    @staticmethod
    def get_position() -> Optional[float]:
        """
        获取当前播放位置（秒）
        
        返回:
            播放位置，如果获取失败返回None
        """
        try:
            result = subprocess.run(
                ['playerctl', 'position'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                # playerctl position 返回的是秒（浮点数）
                position_str = result.stdout.strip()
                if position_str:
                    return float(position_str)
        except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
            pass
        except Exception as e:
            # 调试信息（可选）
            # print(f"获取位置时出错: {e}", file=sys.stderr)
            pass
        
        return None

    @staticmethod
    def get_length() -> Optional[float]:
        """
        获取当前媒体总时长（秒）
        基于 MPRIS: mpris:length（微秒）
        """
        # 方式1：metadata key
        try:
            r = subprocess.run(
                ["playerctl", "metadata", "mpris:length"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if r.returncode == 0 and r.stdout.strip():
                micro = int(float(r.stdout.strip()))
                if micro > 0:
                    return micro / 1_000_000.0
        except Exception:
            pass

        # 方式2：format
        try:
            r = subprocess.run(
                ["playerctl", "metadata", "--format", "{{mpris:length}}"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if r.returncode == 0 and r.stdout.strip():
                micro = int(float(r.stdout.strip()))
                if micro > 0:
                    return micro / 1_000_000.0
        except Exception:
            pass

        return None
    
    @staticmethod
    def is_playing() -> bool:
        """检查是否正在播放"""
        try:
            result = subprocess.run(
                ['playerctl', 'status'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                status = result.stdout.strip().lower()
                return status == 'playing'
        except:
            pass
        
        return False


class LyricFetcher:
    """歌词获取器"""
    
    @staticmethod
    def fetch_lyrics(netease_id: int) -> Tuple[Optional[List[LyricLine]], Optional[List[LyricLine]]]:
        """
        从API获取歌词和翻译
        
        参数:
            netease_id: 网易云音乐ID
        
        返回:
            (歌词列表, 翻译列表) 的元组
        """
        url = f"https://api.vkeys.cn/v2/music/netease/lyric?id={netease_id}"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == 200 and 'data' in data:
                lrc_text = data['data'].get('lrc', '')
                trans_text = data['data'].get('trans', '')
                
                lyrics = LyricParser.parse_lrc(lrc_text) if lrc_text else []
                translations = LyricParser.parse_lrc(trans_text) if trans_text else []
                
                return lyrics, translations
            
        except Exception as e:
            print(f"获取歌词时出错: {e}", file=sys.stderr)
        
        return None, None


class LyricDisplay:
    """歌词显示器"""
    
    @staticmethod
    def clear_screen():
        """清屏"""
        print("\033[2J\033[H", end="")
    
    @staticmethod
    def display_lyrics(
        current_lyric: Optional[str],
        current_trans: Optional[str],
        next_lyric: Optional[str],
        next_trans: Optional[str],
        song_info: SongInfo,
        position: float,
        total_time: Optional[float],
        cfg: AppConfig,
    ):
        """
        显示歌词
        
        参数:
            current_lyric: 当前歌词
            current_trans: 当前翻译
            next_lyric: 下一句歌词
            next_trans: 下一句翻译
            song_info: 歌曲信息
            position: 当前播放位置（秒）
            total_time: 总时长（秒），可选
        """
        print("\033[2J\033[H", end="")

        width = cfg.width
        border = "=" * width

        print(ansi_wrap(border, cfg.colors.get("header_border")))
        artist_display = song_info.artist if song_info.artist else "未知艺术家"
        title_line = f"{artist_display} - {song_info.title}"
        print(ansi_wrap(title_line[:width], cfg.colors.get("song_info")))

        # 进度条
        minutes = int(position // 60)
        seconds = int(position % 60)
        if total_time and total_time > 0:
            total_minutes = int(total_time // 60)
            total_seconds = int(total_time % 60)

            pos = max(0.0, min(position, total_time))
            ratio = pos / total_time
            progress = int(ratio * 100)

            bar_len = cfg.progress_bar_length
            filled = int(round(bar_len * ratio))
            bar = cfg.progress_filled * filled + cfg.progress_empty * (bar_len - filled)
            time_line = f"{minutes:02d}:{seconds:02d} / {total_minutes:02d}:{total_seconds:02d} [{bar}] {progress:3d}%"
        else:
            # 没拿到总时长时，仍显示“占位进度条”
            bar = cfg.progress_empty * cfg.progress_bar_length
            time_line = f"{minutes:02d}:{seconds:02d} / --:-- [{bar}] ---%"

        print(ansi_wrap(time_line[:width], cfg.colors.get("time")))
        print(ansi_wrap(border, cfg.colors.get("header_border")))
        print()

        if current_lyric:
            print(ansi_wrap("━━━ 当前歌词 ━━━", cfg.colors.get("section_title")))
            print()
            print(ansi_wrap(current_lyric, cfg.colors.get("current_lyric")))
            if current_trans:
                print(ansi_wrap(current_trans, cfg.colors.get("current_trans")))
            print()
        else:
            print(ansi_wrap("━━━ 等待歌词... ━━━", cfg.colors.get("dim")))
            print()

        if cfg.show_next and next_lyric:
            print(ansi_wrap("━━━ 下一句 ━━━", cfg.colors.get("dim")))
            print(ansi_wrap(next_lyric, cfg.colors.get("next_lyric")))
            if next_trans:
                print(ansi_wrap(next_trans, cfg.colors.get("next_trans")))

        print()
        sys.stdout.flush()


def main():
    """主函数"""
    cfg = load_config()
    print(f"正在启动歌词追踪器...（配置: {cfg.config_path}）")
    
    searcher = NeteaseMusicSearcher()
    fetcher = LyricFetcher()
    monitor = PlayerctlMonitor()
    
    current_song: Optional[SongInfo] = None
    lyrics: List[LyricLine] = []
    translations: List[LyricLine] = []
    total_time: Optional[float] = None
    last_update_time = 0
    
    try:
        while True:
            # 检查是否正在播放
            if not monitor.is_playing():
                time.sleep(0.5)
                continue
            
            # 获取当前歌曲信息
            song_info = monitor.get_metadata()
            
            if not song_info:
                time.sleep(0.5)
                continue
            
            # 检查是否切换了歌曲
            if current_song is None or current_song.title != song_info.title or current_song.artist != song_info.artist:
                print(f"\n检测到新歌曲: {song_info.artist} - {song_info.title}")
                print("正在搜索歌曲ID...")
                
                netease_id = searcher.search_song(song_info.title, song_info.artist)
                
                if netease_id:
                    print(f"找到歌曲ID: {netease_id}")
                    print("正在获取歌词...")
                    
                    song_info.netease_id = netease_id
                    new_lyrics, new_translations = fetcher.fetch_lyrics(netease_id)
                    
                    if new_lyrics:
                        lyrics = new_lyrics
                        translations = new_translations
                        print(f"成功获取歌词，共 {len(lyrics)} 行")
                    else:
                        print("未能获取歌词")
                        lyrics = []
                        translations = []
                else:
                    print("未找到歌曲ID")
                    lyrics = []
                    translations = []
                
                current_song = song_info
                total_time = monitor.get_length()
                last_update_time = time.time()
            
            # 获取当前播放位置
            position = monitor.get_position()
            if total_time is None and current_song is not None:
                total_time = monitor.get_length()
            
            if position is not None:
                # 获取当前歌词
                current_lyric, next_lyric = LyricParser.get_current_lyric(lyrics, position)
                current_trans, next_trans = LyricParser.get_current_lyric(translations, position)
                
                # 显示歌词（每秒更新一次）
                current_time = time.time()
                if current_time - last_update_time >= cfg.render_interval:
                    LyricDisplay.display_lyrics(
                        current_lyric, current_trans,
                        next_lyric, next_trans,
                        current_song, position, total_time, cfg
                    )
                    last_update_time = current_time
            
            time.sleep(cfg.poll_interval)
            
    except KeyboardInterrupt:
        print("\n\n程序已退出")
        sys.exit(0)
    except Exception as e:
        print(f"\n发生错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
