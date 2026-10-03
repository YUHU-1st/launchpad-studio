"""Build captioned documentation slides from genuine, explicitly labeled UI captures.

Requires the repository Python environment and FFmpeg on PATH. These are silent
screenshot walkthroughs, not screen recordings or physical-hardware footage.
"""
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs/media"
BG = "#0b0e17"
WHITE = "#eef2ff"
MUTED = "#b5bfd5"
ACCENT = "#a78bfa"
FONT = "C:/Windows/Fonts/msyh.ttc"


def text(draw, xy, value, size=26, color=WHITE):
    draw.text(xy, value, font=ImageFont.truetype(FONT, size), fill=color)


def remote_poster():
    poster = Image.new("RGB", (1100, 1200), BG)
    draw = ImageDraw.Draw(poster)
    text(draw, (45, 25), "Launchpad Studio 2.3 · Mobile Remote", 32)
    text(draw, (45, 75), "手机 Studio 与布局 / Responsive web UI", 24, MUTED)
    for index, (name, caption) in enumerate((
        ("remote-studio-2.3.jpg", "Studio · 灯光与电脑性能"),
        ("remote-layout-2.3.jpg", "Layout · 拼接与拖动布局"),
    )):
        picture = Image.open(MEDIA / name).convert("RGB")
        picture = ImageOps.contain(picture, (470, 980), Image.Resampling.LANCZOS)
        poster.paste(picture, (55 + index * 530, 170))
        text(draw, (55 + index * 530, 127), caption, 25, ACCENT)
    text(draw, (45, 1153), "实际网页截图 · 模拟灯板 / Real UI · Simulated pads", 23, MUTED)
    poster.save(MEDIA / "remote-overview-2.3.jpg", quality=92, optimize=True)


def slide_frame(name, title, lines, progress, phone):
    frame = Image.new("RGB", (1280, 900), BG)
    draw = ImageDraw.Draw(frame)
    text(draw, (35, 22), "Launchpad Studio 2.3 · Screenshot walkthrough", 30)
    text(draw, (35, 65), "实际界面截图导览 · 模拟灯板 · 无声 / Real UI · Simulated pads · Silent", 21, MUTED)
    picture = Image.open(MEDIA / name).convert("RGB")
    if phone:
        # Pan long captures without repainting or changing any interface content.
        width = 405
        picture = picture.resize((width, round(picture.height * width / picture.width)), Image.Resampling.LANCZOS)
        height = 715
        offset = round(max(0, picture.height - height) * progress)
        picture = picture.crop((0, offset, width, min(picture.height, offset + height)))
        frame.paste(picture, (45, 120))
        text(draw, (500, 150), title, 34, ACCENT)
        for index, line in enumerate(lines):
            text(draw, (500, 245 + index * 58), line, 24)
        text(draw, (500, 735), "完整截图与操作 / Full captures & guide", 23, MUTED)
        text(draw, (500, 775), "docs/SHOWCASE.md", 23, MUTED)
    else:
        picture = ImageOps.contain(picture, (1200, 665), Image.Resampling.LANCZOS)
        frame.paste(picture, ((1280 - picture.width) // 2, 112))
        text(draw, (40, 790), title, 27, ACCENT)
        text(draw, (40, 832), lines[0], 21)
    draw.rectangle((35, 880, 1245, 885), fill="#232940")
    return frame


def video(filename, slides, phone=False):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("Install FFmpeg or put it on PATH before generating documentation videos.")
    fps, seconds = 12, 6
    process = subprocess.Popen([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
        "-pixel_format", "rgb24", "-video_size", "1280x900", "-framerate", str(fps),
        "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(MEDIA / filename),
    ], stdin=subprocess.PIPE)
    for index, (name, title, lines) in enumerate(slides):
        for tick in range(fps * seconds):
            progress = max(0, min(1, (tick / fps - 1) / (seconds - 2)))
            frame = slide_frame(name, title, lines, progress, phone)
            draw = ImageDraw.Draw(frame)
            fraction = (index + tick / (fps * seconds)) / len(slides)
            draw.rectangle((35, 880, 35 + round(1210 * fraction), 885), fill=ACCENT)
            process.stdin.write(frame.tobytes())
    process.stdin.close()
    if process.wait():
        raise SystemExit(f"FFmpeg failed while creating {filename}")
    print(f"Created {filename}: {len(slides) * seconds}s, H.264, silent screenshot walkthrough")


if __name__ == "__main__":
    remote_poster()
    video("layout-demo.mp4", [
        ("layout-2.3.jpg", "1 / 扩展画布 · Extended 16×8", ["在模式页统一开始 / Start the shared show from its feature page"]),
        ("layout-mirror-2.3.jpg", "2 / 复制画面 · Mirror", ["每块灯板显示相同内容 / Each pad shows the same frame"]),
        ("layout-independent-2.3.jpg", "3 / 独立模式 · Independent", ["逐台分配功能；同功能共享参数 / Per-device functions, shared settings per engine"]),
        ("layout-swap-2.3.jpg", "4 / 交换位置 · Swap tiles", ["拖到另一台板块交换位置 / Drag onto another tile to swap positions"]),
        ("layout-vertical-2.3.jpg", "5 / 竖向扩展 · Extended 8×16", ["按实体摆放排布，预览比例随之改变 / Match physical placement; the canvas aspect follows"]),
    ])
    video("presets-demo.mp4", [
        ("parameters-2.3.jpg", "1 / 调整细节 · Tune the response", ["频谱、响度、灵敏度、噪声门限 / Frequency, loudness, sensitivity and noise gate"]),
        ("presets-2.3.jpg", "2 / 保存预设 · Save a named preset", ["点击保存并输入名称；同名会替换 / Save with a name; saving the same name replaces it"]),
        ("presets-2.3.jpg", "3 / 加载与最近使用 · Load and recent presets", ["选择名称后加载；最近五项优先 / Select then load; five recent names appear first"]),
        ("parameters-2.3.jpg", "4 / 跨模式复制 · Copy compatible settings", ["音乐与拾音共享音频参数；只粘贴匹配字段 / Music/live share audio fields; only matching parameters transfer"]),
        ("presets-2.3.jpg", "5 / 恢复默认与记忆 · Defaults and persistence", ["默认只重置当前页细节；修改自动记忆 / Defaults resets this page; changes persist automatically"]),
    ])
    video("remote-demo.mp4", [
        ("remote-studio-2.3.jpg", "1 / Studio", ["同一局域网 + 六位 PIN", "Same LAN + six-digit PIN", "全局颜色、亮度与非游戏功能", "Colors, brightness and non-game modes"]),
        ("remote-layout-2.3.jpg", "2 / 布局 Layout", ["扩展 / 复制 / 独立", "Extended / Mirror / Independent", "拖动版块，实机编号辨认", "Drag tiles and identify pad numbers"]),
        ("remote-macros-2.3.jpg", "3 / 宏 Macros", ["点选、编辑、保存或清除", "Select, edit, save or clear", "按键会触发已配置的电脑操作", "Configured buttons trigger PC actions"]),
        ("remote-media-2.3.jpg", "4 / Windows 媒体", ["示例封面、标题与播放进度", "Sample artwork, title and timeline", "系统音量、静音、默认输出", "PC volume, mute and audio output", "播放器能力取决于 GSMTC", "Capabilities depend on the player"]),
        ("remote-vj-2.3.jpg", "5 / VJ 多目标", ["屏幕与灯板分别多选", "Separate screen and pad targets", "16×8 LEDs / 1920×1080 video", "原生灯效与视频图形独立", "Independent LED and video graphics"]),
    ], phone=True)
