"""Private documentation preview: sample data and simulated pads, never real MIDI.

Run with the repository Python environment. Capture the displayed application
and its mobile web UI; this fixture does not read personal settings or media.
"""
import multiprocessing
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from core.launchpad import LaunchpadDevice
from core.settings import Settings
from core.windows_media import SystemMediaBridge


if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = Path(__file__).resolve().parents[1]
    (root / "build").mkdir(exist_ok=True)
    app.ROOT = Path(tempfile.mkdtemp(prefix="docs-preview-", dir=root / "build"))
    settings = Settings(app.ROOT / "data/settings.json")
    settings.data["remote"]["port"] = 8879
    settings.data["presets"]["audio"] = {"Neon Stage / 霓虹舞台": dict(settings.data["detail_params"]["music"])}
    settings.data["macros"] = {
        "pad:0:1": {"action": "热键", "value": "CTRL+SHIFT+S", "color": "#a78bfa"},
        "pad:1:1": {"action": "媒体控制", "value": "PLAY", "color": "#22d3ee"},
        "pad:2:1": {"action": "打开网址", "value": "https://github.com/YUHU-1st/launchpad-studio", "color": "#fbbf24"},
        "pad:3:1": {"action": "输入文字", "value": "Launchpad Studio", "color": "#fb7185"},
    }
    settings.save()
    # Do not enumerate MIDI or inspect the user's Windows media sessions.
    LaunchpadDevice.devices = staticmethod(lambda: ([], []))
    app.LaunchpadStudio._start_tray = lambda self: None
    SystemMediaBridge.start = lambda self: None
    window = app.LaunchpadStudio()
    window.protocol("WM_DELETE_WINDOW", window._close)
    window.title("Launchpad Studio 2.3 · DOCS PREVIEW · 示例数据 / 模拟灯板")
    window.geometry("1440x880+20+20")
    window.launchpads = {}
    items = []
    for index, model in enumerate(("x", "mk2")):
        device = LaunchpadDevice(model=model)
        device.connected = True
        device.out = SimpleNamespace(sysex=lambda _message: None, short=lambda *_args: None, close=lambda: None)
        device_id = f"demo-{model}"
        window.launchpads[device_id] = device
        items.append({"id": device_id, "number": index + 1, "x": index, "y": 0, "mode": "性能监控", "model": model})
    window.lp = next(iter(window.launchpads.values()))
    window.multi_cfg.update(enabled=True, link_mode="扩展画布", devices=items)
    window._connected_ui()
    window.device_status.configure(text="DOCS · 2 台模拟设备")
    window.settings_store.data["vj"].update(launchpads=[item["id"] for item in items], map_launchpad=True)
    # A paused example session makes the media UI visible without controlling a player.
    window.system_media._state.update(available=True, app="Documentation example", title="DEMO · Neon Pulse",
        artist="Launchpad Studio", album="Sample metadata / 示例数据", duration=210, position=48, can_seek=True,
        cover_id="docs-cover", lyric_line="Demo lighting · 霓虹舞台", lyric_next="Sample text / 示例字幕",
        controls=dict.fromkeys(("play", "pause", "toggle", "previous", "next", "stop", "repeat", "shuffle"), True))
    window.system_media._covers["docs-cover"] = (b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#0b1021"/><circle cx="100" cy="100" r="65" fill="none" stroke="#a78bfa" stroke-width="8"/><path d="M35 100H65L80 65L100 140L120 75L135 100H165" fill="none" stroke="#22d3ee" stroke-width="8"/><text x="100" y="182" text-anchor="middle" fill="#ffffff" font-size="14">NEON PULSE / DEMO</text></svg>', "image/svg+xml")
    window.system_media._state["audio"].update(available=True, volume=35, mute=False, active_output="demo-speakers",
        outputs=[{"id": "demo-speakers", "name": "DEMO · Speakers"}, {"id": "demo-usb", "name": "DEMO · USB audio"}])
    window._start_perf()
    window._show_mode("布局设置")
    window.after(3_600_000, window._close)
    print(str(app.ROOT), flush=True)
    window.mainloop()
