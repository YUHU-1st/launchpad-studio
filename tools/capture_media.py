"""Capture real Launchpad Studio UI screenshots and an all-mode README demo."""
from __future__ import annotations

import colorsys
from datetime import datetime
import tempfile
import time
from pathlib import Path
import sys
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from core.audio_engine import reactive_frame
from core.launchpad import ALL_PADS
from core.miniapps import calendar_frame, clock_frame, scrolling_text, weather_frame
from core.rhythm import RhythmGame, chart_from_analysis


OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "media"


def capture(window):
    window.update_idletasks(); window.update(); time.sleep(.025)
    x, y = window.winfo_rootx(), window.winfo_rooty()
    screen = ImageGrab.grab(); sx = screen.width/window.winfo_screenwidth(); sy = screen.height/window.winfo_screenheight()
    box = (round(x*sx), round(y*sy), round((x+window.winfo_width())*sx), round((y+window.winfo_height())*sy))
    return screen.crop(box).resize((window.winfo_width(), window.winfo_height())).convert("RGB")


def performance_demo(window, phase):
    stats = {"CPU": 45+35*np.sin(phase), "RAM": 62, "磁盘": 38, "GPU": 55+35*np.cos(phase*.8),
             "网络 MB/s": 4.8, "磁盘 MB/s": 12.5, "cores": [35,55,72,48,80,42,67,30],
             "temperatures": {"CPU": 67.0, "GPU": 61.0, "主板": 43.0, "存储": 48.0}}
    for key, label in window.metric_labels.items():
        value = stats[key]; label.configure(text=f"{value:.1f}%" if key in ("CPU", "RAM", "GPU", "磁盘") else f"{value:.1f}")
    for key, label in window.temp_labels.items(): label.configure(text=f"{stats['temperatures'][key]:.1f} °C", fg=app.GOOD)
    window.apply_frame(window.performance.frame(stats, "霓虹", .9))


def pixel_video_frame(phase):
    frame = {}
    for x, y in ALL_PADS:
        hue = (x/12+y/18+phase*.035) % 1; value = .28+.72*max(0, np.sin(x*.75+y*.5+phase))
        frame[(x, y)] = tuple(round(c*255) for c in colorsys.hsv_to_rgb(hue, .82, value))
    return frame


def demo_audio(phase, size=4096, sr=44100):
    t = np.arange(size)/sr; envelope = .28+.16*(1+np.sin(phase*1.7))
    return (envelope*(np.sin(2*np.pi*110*t)+.62*np.sin(2*np.pi*440*t)+.35*np.sin(2*np.pi*1760*t))).astype(np.float32)


def save_still(window, name):
    image = capture(window); image.save(OUTPUT/name, optimize=True); return image


def append_frames(window, frames, renderer, count=8):
    for phase in np.linspace(0, 6, count):
        window.apply_frame(renderer(float(phase))); frames.append(capture(window))


def write_video(path, frames, fps=10):
    width, height = frames[0].size
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    for frame in frames: writer.write(cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2BGR))
    writer.release()


def macro_frame(window, phase):
    result = {}
    for x, y in window.lp.pads:
        macro = window._macro_get(x, y)
        if not macro: result[(x, y)] = (0, 0, 0); continue
        text = macro.get("color", "#000000").lstrip("#")
        base = tuple(int(text[i:i+2], 16) for i in (0, 2, 4)); power = .62+.38*np.sin(phase+x*.7+y*.45)**2
        result[(x, y)] = tuple(round(c*power) for c in base)
    return result


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app.LaunchpadStudio._start_tray = lambda self: None
    app.LaunchpadDevice.devices = staticmethod(lambda: ([], []))
    app.audio_devices = lambda: [("input:0", "系统声音 · Demo WASAPI Loopback"), ("input:1", "麦克风 · Demo")]
    with tempfile.TemporaryDirectory() as temp:
        app.ROOT = Path(temp)
        window = app.LaunchpadStudio(); window.geometry("1280x820+30+30"); window.deiconify(); window.lift(); window.update()
        frames, clips = [], {}

        start = len(frames)
        window._show_mode("性能监控"); performance_demo(window, .4); save_still(window, "overview.png")
        for phase in np.linspace(0, 5, 8): performance_demo(window, float(phase)); frames.append(capture(window))
        clips["performance"] = frames[start:]

        start = len(frames)
        demos = [((0,1), "热键", "CTRL+SHIFT+S", "#7c5cff"), ((1,1), "媒体控制", "PLAY", "#22d3ee"),
                 ((2,1), "系统操作", "截图", "#34d399"), ((3,1), "打开网址", "github.com", "#f59e0b"),
                 ((4,1), "设置音量", "35", "#fb7185"), ((5,1), "鼠标操作", "双击", "#60a5fa"),
                 ((6,1), "输入文字", "Launchpad Studio", "#c084fc"), ((7,1), "组合动作", "hotkey: CTRL+L", "#f472b6")]
        window.settings_store.data["macros"] = {window.lp.macro_key(x, y): {"action": a, "value": v, "color": c} for (x,y),a,v,c in demos}
        window._show_mode("宏按键"); window._load_macro_form(0, 1); window._render_macro_profile(); save_still(window, "macros.png")
        append_frames(window, frames, lambda p: macro_frame(window, p), 7)
        clips["macros"] = frames[start:]

        start = len(frames)
        window.video_playlist = ["Neon_City_Demo.mp4", "Launchpad_Pixel_Loop.webm"]; window.video_index = 0; window._show_mode("视频播放")
        window.video_time.configure(text="01:24 / 03:48"); window.video_progress.set(368); window.video_effect.set("镜像万花筒")
        window.video_rate.set("1.25×"); window.video_loop.set("列表循环"); window.video_list.selection_set(0)
        window.apply_frame(pixel_video_frame(1.7)); save_still(window, "video-player.png"); append_frames(window, frames, pixel_video_frame, 9)
        clips["video-player"] = frames[start:]

        start = len(frames)
        window.audio_playlist = ["Midnight_Pulse.wav", "Aurora_Drive.flac"]; window.audio_index = 0; window._show_mode("音乐演示")
        window.audio_list.selection_set(0); window.analysis_label.configure(text="BPM 128  ·  明亮 / 高能  ·  舞曲 / 电子\n能量 86%")
        window.audio_time.configure(text="02:16 / 04:32"); window.audio_progress.set(500); window.music_style.set("频谱")
        music_render = lambda p: reactive_frame(demo_audio(p), 44100, "频谱", "霓虹", .95, p*6,
                                                 {"sensitivity": 1.45, "threshold": .006, "freq_min": 40, "freq_max": 16000})
        window.apply_frame(music_render(2)); save_still(window, "music-show.png"); append_frames(window, frames, music_render, 9)
        clips["music-show"] = frames[start:]

        start = len(frames)
        window._show_mode("实时拾音"); window.live_combo.current(0); window.live_style.set("星云")
        live_render = lambda p: reactive_frame(demo_audio(p), 44100, "星云", "海洋", .92, p*8,
                                                {"sensitivity": 1.6, "threshold": .004, "speed": 1.4, "spread": 1.35})
        window.apply_frame(live_render(1)); save_still(window, "live-audio.png"); append_frames(window, frames, live_render, 9)
        clips["live-audio"] = frames[start:]

        start = len(frames)
        window._show_mode("工具与游戏"); window.utility_choice.set("数字时钟"); window._build_utility_options(); window.utility_info.configure(text="23:48:16")
        low, high = window._utility_colors()
        clock_render = lambda p: clock_frame(datetime(2026, 9, 10, 23, 48, int(p*8)%60), int(p), low, high)
        window.apply_frame(clock_render(1)); save_still(window, "utilities.png"); append_frames(window, frames, clock_render, 4)
        utility_demos = [
            ("日历", "2026年09月10日 · 星期四", lambda p: calendar_frame(datetime(2026,9,10), int(p), low, high)),
            ("天气", "上海\n晴间多云  26.4 °C（体感 27.1 °C）\n最高 29.0°  最低 22.0°  降水 10%", lambda p: weather_frame(1, 26.4, low, high)),
            ("专注计时器", "24:37", lambda p: scrolling_text("24:37", int(p), low, high)),
        ]
        for choice, info, renderer in utility_demos:
            window.utility_choice.set(choice); window._build_utility_options(); window.utility_info.configure(text=info)
            append_frames(window, frames, renderer, 4)
        clips["desktop-utilities"] = frames[start:]

        start = len(frames)
        window.utility_choice.set("贪吃蛇"); window._build_utility_options(); window.game_difficulty.set("普通")
        window.snake.reset(); window.snake.snake = [(5,4),(4,4),(3,4),(2,4),(1,4)]; window.snake.food = (6,6); window.snake.score = 12
        window.utility_info.configure(text="得分 12 · 第 3 关\n最高 37"); window.apply_frame(window.snake.frame()); save_still(window, "casual-games.png")
        for phase in np.linspace(0, 6, 7):
            pulse = window.snake.frame()
            for xy, color in list(pulse.items()): pulse[xy] = tuple(round(c*(.72+.28*np.sin(phase)**2)) for c in color)
            window.apply_frame(pulse); frames.append(capture(window))
        clips["snake"] = frames[start:]

        start = len(frames)
        window.utility_choice.set("打地鼠"); window._build_utility_options(); window.game_difficulty.set("简单")
        window.mole.reset(8); window.mole.score = 9; window.mole.misses = 2; window.mole.target = (4, 3)
        window.utility_info.configure(text="得分 9 · 第 2 关\n剩余机会 6/8 · 最高 28")
        window.apply_frame(window.mole.frame()); save_still(window, "whack-a-mole.png")
        for x, y in ((4,3),(1,7),(6,2),(3,5),(7,8),(0,4),(5,6)):
            window.mole.target = (x, y); window.apply_frame(window.mole.frame()); frames.append(capture(window))
        clips["whack-a-mole"] = frames[start:]

        sr = 8000; t = np.arange(sr*7)/sr; samples = (np.sin(2*np.pi*220*t)*.04).astype(np.float32)
        for second in range(1,7): samples[second*sr:second*sr+350] += .8*np.hanning(350).astype(np.float32)
        analysis = SimpleNamespace(data=samples, sr=sr, duration=7.0, bpm=120)
        for style, filename, position in (("瀑布音游", "waterfall-game.png", 2.6), ("环形音游", "rhythm-game.png", 2.25)):
            start = len(frames)
            chart = chart_from_analysis(analysis, "Midnight_Pulse.wav", style, "普通", 8); game = RhythmGame(); game.reset(chart, 3, "普通")
            window.utility_choice.set(style); window._build_utility_options(); window.rhythm_file_label.configure(text="Midnight_Pulse.wav")
            window.utility_info.configure(text=f"谱面已生成 · BPM {chart.bpm} · {len(chart.notes)} 个音符 · 8 键\n得分 12600 · 连击 18 · 准确率 96.4%")
            window.apply_frame(game.frame(position, low, high, .95)); save_still(window, filename)
            for playhead in np.linspace(.5, 6.2, 10):
                game.update(float(playhead)); window.apply_frame(game.frame(float(playhead), low, high, .95)); frames.append(capture(window))
            clips["waterfall" if style == "瀑布音游" else "radial-rhythm"] = frames[start:]

        width, height = frames[0].size
        write_video(OUTPUT/"launchpad-studio-demo.mp4", frames)
        for name, clip_frames in clips.items(): write_video(OUTPUT/f"{name}-demo.mp4", clip_frames, 5)
        gif = [frame.resize((768, round(height*768/width))) for frame in frames[::2]]
        gif[0].save(OUTPUT/"launchpad-studio-demo.gif", save_all=True, append_images=gif[1:], duration=200, loop=0, optimize=True)
        window._close()
    print(f"Captured {len(frames)} frames and {len(clips)} feature videos in {OUTPUT}")


if __name__ == "__main__": main()
