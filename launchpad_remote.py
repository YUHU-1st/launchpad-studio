from __future__ import annotations

import ctypes
import copy
import logging
from pathlib import Path
import queue
import secrets
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import app as desktop
from core.audio_engine import LiveAudio, audio_devices
from core.remote import RemoteServer
from core.windows_media import SystemMediaBridge


UTILITY_ALLOWED = ("数字时钟", "日历", "天气", "专注计时器")
VIDEO_RATES = ("0.50×", "0.75×", "1.00×", "1.25×", "1.50×", "2.00×", "3.00×")
LOOPS = ("不循环", "单曲循环", "列表循环")
VIDEO_EFFECTS = ("原色视频", "亮度热图", "边缘轮廓", "单色辉光", "镜像万花筒", "像素故障")


class RemoteLaunchpadStudio(desktop.LaunchpadStudio):
    """Desktop application plus the authenticated LAN/Android remote surface."""

    def __init__(self):
        self._remote_commands: queue.Queue[tuple[str, object]] = queue.Queue()
        self._remote_state_lock = threading.Lock()
        self._remote_state_cache: dict = {}
        self._remote_perf_stats: dict = {}
        self._remote_live_devices: list[tuple[object, str]] = []
        self.remote_server = None
        self.system_media = None
        super().__init__()

        remote_cfg = self.settings_store.data.setdefault("remote", {})
        remote_cfg.setdefault("enabled", True)
        remote_cfg.setdefault("port", 8765)
        pin = str(remote_cfg.get("pin", ""))
        if not (pin.isdigit() and len(pin) == 6):
            remote_cfg["pin"] = f"{secrets.randbelow(1_000_000):06d}"
            self.settings_store.save()

        # Capture performance samples without duplicating the base UI tick.
        original_sample = self.performance.sample
        def sample_with_remote_cache():
            stats = original_sample()
            self._remote_perf_stats = copy.deepcopy(stats)
            return stats
        self.performance.sample = sample_with_remote_cache

        self._refresh_remote_live_devices()
        self.system_media = SystemMediaBridge()
        self.system_media.start()
        self.remote_server = RemoteServer(
            web_root=desktop.BUNDLE_ROOT / "remote",
            pin=remote_cfg["pin"],
            port=int(remote_cfg.get("port", 8765)),
            state_provider=self._remote_server_state,
            command_sink=self._enqueue_remote_command,
            media_bridge=self.system_media,
        )
        if remote_cfg.get("enabled", True):
            self.remote_server.start()
        self.after(100, self._remote_tick)

    def _build_ui(self):
        super()._build_ui()
        try:
            top = self.winfo_children()[0]
            ttk.Button(top, text="手机遥控", command=self._remote_dialog).pack(side="right", padx=8, pady=12)
        except Exception:
            logging.debug("Could not add remote button", exc_info=True)

    def _remote_cfg(self) -> dict:
        return self.settings_store.data.setdefault("remote", {"enabled": True, "port": 8765, "pin": ""})

    def _enqueue_remote_command(self, action: str, value):
        self._remote_commands.put((action, value))

    def _remote_server_state(self) -> dict:
        with self._remote_state_lock:
            return copy.deepcopy(self._remote_state_cache)

    def _remote_tick(self):
        if self._closing:
            return
        for _ in range(30):
            try:
                action, value = self._remote_commands.get_nowait()
            except queue.Empty:
                break
            try:
                self._dispatch_remote_command(action, value)
            except Exception as exc:
                logging.exception("Remote command failed: %s", action)
                self.set_status(f"手机遥控命令失败：{exc}")
        try:
            state = self._build_remote_state()
            with self._remote_state_lock:
                self._remote_state_cache = state
        except Exception:
            logging.debug("Remote state snapshot failed", exc_info=True)
        self.after(200, self._remote_tick)

    def _detail_state(self, mode: str) -> dict:
        values = dict(self.settings_store.data.get("detail_params", {}).get(mode, {}))
        try:
            snapshot = self._detail_snapshot(mode)
            if snapshot:
                values.update(snapshot)
        except Exception:
            pass
        return values

    def _build_remote_state(self) -> dict:
        video_running = bool(self.video.thread and self.video.thread.is_alive())
        music_running = bool(self.music and self.music.worker and self.music.worker.is_alive())
        live_running = bool(self.live and self.live.worker and self.live.worker.is_alive())
        music_position = 0.0
        music_duration = float(self.audio_duration or 0.0)
        music_analysis = {}
        if self.music and self.music.analysis:
            try:
                with self.music.lock:
                    music_position = float(self.music.cursor / self.music.analysis.sr)
                a = self.music.analysis
                music_duration = float(a.duration)
                music_analysis = {"bpm": a.bpm, "mood": a.mood, "genre": a.genre, "energy": a.energy}
            except Exception:
                pass

        macros = []
        for x, y in self.lp.pads:
            item = dict(self._macro_get(x, y) or {})
            macros.append({
                "x": x, "y": y, "label": self.lp.pad_label(x, y),
                "configured": bool(item),
                "action": item.get("action", "热键"),
                "value": item.get("value", ""),
                "color": item.get("color", "#7c5cff"),
            })

        utility_cfg = self.settings_store.data.get("utilities", {})
        selected = self.active_utility if self.active_utility in UTILITY_ALLOWED else utility_cfg.get("selected", "数字时钟")
        if selected not in UTILITY_ALLOWED:
            selected = "数字时钟"
        focus_remaining = int(self.focus_remaining or int(utility_cfg.get("focus_minutes", 25)) * 60)
        models = [{"key": "auto", "name": "自动识别"}] + [{"key": m.key, "name": m.name} for m in desktop.MODELS]
        return {
            "mode": self.mode,
            "active_mode": self.active_mode,
            "status": self.status_var.get(),
            "global": {
                "palette": self.palette_var.get(),
                "palettes": list(desktop.PALETTES.keys()),
                "brightness": round(float(self.brightness.get()), 1),
                "custom_color": self.custom_color,
                "macro_control": bool(self.settings_store.data.get("macro_control_enabled", False)),
            },
            "launchpad": {
                "connected": bool(self.lp.connected),
                "model": self.lp.model.name,
                "model_key": self.settings_store.data.get("launchpad_model", "auto"),
                "models": models,
                "inputs": list(getattr(self, "midi_inputs", [])),
                "outputs": list(getattr(self, "midi_outputs", [])),
            },
            "performance": copy.deepcopy(self._remote_perf_stats),
            "macros": macros,
            "video": {
                "playlist": [Path(p).name for p in self.video_playlist],
                "index": self.video_index,
                "running": video_running,
                "paused": bool(self.video.paused) if video_running else False,
                "position": float(self.video.position or 0.0),
                "duration": float(self.video.duration or self.video_duration or 0.0),
                "detail": self._detail_state("video"),
            },
            "music": {
                "playlist": [Path(p).name for p in self.audio_playlist],
                "index": self.audio_index,
                "running": music_running,
                "paused": bool(self.music.paused) if self.music else False,
                "position": music_position,
                "duration": music_duration,
                "analysis": music_analysis,
                "detail": self._detail_state("music"),
            },
            "live": {
                "running": live_running,
                "devices": [{"id": str(device_id), "name": name} for device_id, name in self._remote_live_devices],
                "selected": self.settings_store.data.get("live_device", ""),
                "detail": self._detail_state("live"),
            },
            "utilities": {
                "allowed": list(UTILITY_ALLOWED),
                "selected": selected,
                "running": bool(self.utility_running and self.active_utility in UTILITY_ALLOWED),
                "weather_city": utility_cfg.get("weather_city", "北京"),
                "focus_minutes": int(utility_cfg.get("focus_minutes", 25)),
                "focus_remaining": focus_remaining,
                "focus_paused": bool(self.focus_paused),
            },
            "presets": {
                "video": self._preset_names("video"),
                "music": self._preset_names("music"),
                "live": self._preset_names("live"),
            },
        }

    def _refresh_remote_live_devices(self):
        try:
            self._remote_live_devices = list(audio_devices())
        except Exception:
            self._remote_live_devices = []

    def _prepare_page(self, name: str):
        if self.mode != name:
            self._show_mode(name)

    def _update_custom_color(self, value: str):
        value = str(value or "")
        if not (len(value) == 7 and value.startswith("#")):
            raise ValueError("颜色必须为 #RRGGBB")
        h = value[1:]
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        self.custom_color = value
        self.settings_store.data["custom_color"] = value
        desktop.PALETTES["自定义"] = (tuple(int(v * .18) for v in rgb), rgb)
        self.palette_var.set("自定义")
        self._palette_changed()

    def _set_detail(self, mode: str, updates: dict):
        if mode not in ("video", "music", "live"):
            raise ValueError("未知参数模式")
        clean = {str(k): v for k, v in dict(updates or {}).items()}
        self.settings_store.data["detail_params"][mode].update(clean)
        self.settings_store.save()
        if mode == "video":
            detail = self.settings_store.data["detail_params"]["video"]
            params = {k: detail.get(k) for k in ("saturation", "contrast", "gamma", "edge_threshold")}
            params["brightness"] = self.brightness.get() / 100
            h = self.custom_color.lstrip("#")
            params["tint"] = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
            self.video.set_effect(detail.get("effect", "原色视频"), params)
            if "rate" in clean:
                self.video.set_rate(self._rate(str(clean["rate"])))
        elif mode == "music" and self.music:
            detail = self.settings_store.data["detail_params"]["music"]
            if "volume" in clean:
                self.music.set_volume(float(detail.get("volume", 85)) / 100)
            if "rate" in clean:
                self.music.set_rate(self._rate(str(detail.get("rate", "1.00×"))))
            self.music.set_visual(detail.get("style", "频谱"), self.palette_var.get(), self.brightness.get() / 100, detail)
        elif mode == "live" and self.live:
            detail = self.settings_store.data["detail_params"]["live"]
            self.live.set_visual(detail.get("style", "星云"), self.palette_var.get(), self.brightness.get() / 100, detail)

    def _dispatch_remote_command(self, action: str, value):
        if action == "app.stop":
            self._stop_all(); return
        if action == "app.blackout":
            self._stop_all_and_clear(); return
        if action == "app.test_lights":
            if not self.lp.connected:
                raise RuntimeError("Launchpad 未连接")
            self._test_lights(); return
        if action == "global.palette":
            if value not in list(desktop.PALETTES.keys()):
                raise ValueError("未知配色")
            self.palette_var.set(value); self._palette_changed(); return
        if action == "global.brightness":
            self.brightness.set(max(10, min(100, float(value)))); self._brightness_changed(); return
        if action == "global.custom_color":
            self._update_custom_color(str(value)); return
        if action == "macro_control":
            enabled = bool(value); self.settings_store.data["macro_control_enabled"] = enabled; self.settings_store.save()
            if hasattr(self, "macro_control_var"): self.macro_control_var.set(enabled)
            return
        if action == "performance.start":
            self._start_perf(); return

        if action.startswith("macro."):
            payload = dict(value or {})
            if action == "macro.start":
                self._start_macros(); return
            x, y = int(payload.get("x", 0)), int(payload.get("y", 1))
            if (x, y) not in self.lp.pads:
                raise ValueError("无效 Launchpad 按键")
            if action == "macro.trigger":
                macro = self._macro_get(x, y)
                if macro: self.macro_exec.execute(macro)
                return
            key = self._macro_key(x, y)
            if action == "macro.save":
                self.settings_store.data["macros"][key] = {
                    "action": str(payload.get("action", "热键")),
                    "value": str(payload.get("value", "")),
                    "color": str(payload.get("color", "#7c5cff")),
                }
            elif action == "macro.clear":
                self.settings_store.data["macros"].pop(key, None)
                self.settings_store.data["macros"].pop(str(self.lp.pad_id(x, y)), None)
            self.settings_store.save()
            if self.active_mode == "宏按键": self._render_macro_profile()
            return

        if action.startswith("video."):
            if action == "video.select":
                self.video_index = max(0, min(len(self.video_playlist) - 1, int(value))) if self.video_playlist else -1; return
            if action in ("video.play", "video.pause", "video.previous", "video.next"):
                self._prepare_page("视频播放")
                if action == "video.play":
                    if self.video.thread and self.video.thread.is_alive() and self.video.paused: self._video_pause()
                    elif not (self.video.thread and self.video.thread.is_alive()): self._start_video()
                elif action == "video.pause":
                    if self.video.thread and self.video.thread.is_alive(): self._video_pause()
                    else: self._start_video()
                else:
                    self._advance_video(-1 if action.endswith("previous") else 1)
                return
            if action == "video.seek": self.video.seek(float(value)); return
            if action == "video.rate":
                if str(value) not in VIDEO_RATES: raise ValueError("无效播放速度")
                self._set_detail("video", {"rate": str(value)}); return
            if action == "video.loop":
                if str(value) not in LOOPS: raise ValueError("无效循环模式")
                self._set_detail("video", {"loop": str(value)}); return
            if action == "video.effect":
                if str(value) not in VIDEO_EFFECTS: raise ValueError("无效视频滤镜")
                self._set_detail("video", {"effect": str(value)}); return
            if action == "video.param": self._set_detail("video", dict(value or {})); return

        if action.startswith("music."):
            if action == "music.select":
                self.audio_index = max(0, min(len(self.audio_playlist) - 1, int(value))) if self.audio_playlist else -1; return
            if action in ("music.play", "music.pause", "music.previous", "music.next"):
                self._prepare_page("音乐演示")
                running = bool(self.music and self.music.worker and self.music.worker.is_alive())
                if action == "music.play":
                    if running and self.music.paused: self._audio_pause()
                    elif not running: self._start_music()
                elif action == "music.pause":
                    if running: self._audio_pause()
                    else: self._start_music()
                else:
                    self._advance_audio(-1 if action.endswith("previous") else 1)
                return
            if action == "music.seek":
                if self.music: self.music.seek(float(value))
                return
            if action == "music.rate":
                if str(value) not in VIDEO_RATES: raise ValueError("无效播放速度")
                self._set_detail("music", {"rate": str(value)}); return
            if action == "music.loop":
                if str(value) not in LOOPS: raise ValueError("无效循环模式")
                self._set_detail("music", {"loop": str(value)}); return
            if action == "music.volume": self._set_detail("music", {"volume": max(0, min(100, float(value)))}); return
            if action == "music.style":
                if str(value) not in self._visual_styles(): raise ValueError("无效灯效")
                self._set_detail("music", {"style": str(value)}); return
            if action == "music.param": self._set_detail("music", dict(value or {})); return

        if action.startswith("live."):
            if action == "live.refresh": self._refresh_remote_live_devices(); return
            if action == "live.device":
                selected = next(((dev, name) for dev, name in self._remote_live_devices if str(dev) == str(value)), None)
                if not selected: raise ValueError("未找到输入设备")
                self.settings_store.data["live_device"] = selected[1]; self.settings_store.save(); return
            if action == "live.start":
                if not self._remote_live_devices: self._refresh_remote_live_devices()
                saved_name = self.settings_store.data.get("live_device", "")
                selected = next((item for item in self._remote_live_devices if item[1] == saved_name), self._remote_live_devices[0] if self._remote_live_devices else None)
                if not selected: raise RuntimeError("没有可用音频输入设备")
                detail = self._detail_state("live")
                self._activate_mode("实时拾音")
                if not self.live: self.live = LiveAudio(self.submit_frame, self.set_status)
                self.live.start(selected[0], detail.get("style", "星云"), self.palette_var.get(), self.brightness.get()/100, detail)
                return
            if action == "live.stop":
                if self.live: self.live.stop()
                if self.active_mode == "实时拾音": self.active_mode = None
                return
            if action == "live.style":
                if str(value) not in self._visual_styles(): raise ValueError("无效灯效")
                self._set_detail("live", {"style": str(value)}); return
            if action == "live.param": self._set_detail("live", dict(value or {})); return

        if action.startswith("utility."):
            cfg = self.settings_store.data["utilities"]
            if action == "utility.select":
                if value not in UTILITY_ALLOWED: raise ValueError("手机端不提供游戏控制")
                cfg["selected"] = value; self.settings_store.save(); return
            if action == "utility.weather_city": cfg["weather_city"] = str(value).strip() or "北京"; self.settings_store.save(); return
            if action == "utility.focus_minutes": cfg["focus_minutes"] = max(1, min(180, int(value))); self.settings_store.save(); return
            if action == "utility.start":
                choice = cfg.get("selected", "数字时钟")
                if choice not in UTILITY_ALLOWED: raise ValueError("手机端不提供游戏控制")
                self._prepare_page("工具与游戏")
                self.utility_choice.set(choice); self._utility_selection_changed()
                if choice == "天气": self.weather_city.set(cfg.get("weather_city", "北京"))
                if choice == "专注计时器": self.focus_minutes.set(int(cfg.get("focus_minutes", 25)))
                self._start_utility(); return
            if action == "utility.stop":
                if self.active_utility in UTILITY_ALLOWED: self._stop_utility(clear=False)
                return
            if action == "utility.focus_pause": self._pause_focus(); return
            if action == "utility.focus_reset":
                if not hasattr(self, "focus_minutes"): self._prepare_page("工具与游戏")
                self._reset_focus(); return

        if action.startswith("preset."):
            payload = dict(value or {}); mode = str(payload.get("mode", "")); name = str(payload.get("name", "")).strip()
            if mode not in ("video", "music", "live") or not name: raise ValueError("无效预设")
            group = self._preset_group(mode)
            if action == "preset.load":
                values = self.settings_store.data["presets"][group].get(name)
                if values is None: raise ValueError("预设不存在")
                self._prepare_page({"video":"视频播放", "music":"音乐演示", "live":"实时拾音"}[mode])
                self._apply_detail_snapshot(mode, values)
                self._touch_recent(mode, name); self.settings_store.save(); return
            self.settings_store.data["presets"][group][name] = self._detail_state(mode)
            self._touch_recent(mode, name); self.settings_store.save(); return

        if action == "device.refresh": self._refresh_midi(); return
        if action == "device.connect":
            payload = dict(value or {}); self._refresh_midi()
            in_name, out_name = str(payload.get("input", "")), str(payload.get("output", ""))
            if in_name not in self.midi_inputs or out_name not in self.midi_outputs: raise ValueError("MIDI 端口不存在")
            model = str(payload.get("model", "auto"))
            self.lp.connect(self.midi_inputs.index(in_name), self.midi_outputs.index(out_name), model)
            self.settings_store.data["launchpad_model"] = model; self.settings_store.save(); self._connected_ui(); return
        raise ValueError(f"不支持的远程命令：{action}")

    def _remote_dialog(self):
        cfg = self._remote_cfg()
        win = tk.Toplevel(self); win.title("手机遥控"); win.geometry("500x390"); win.configure(bg=desktop.BG); win.transient(self)
        tk.Label(win, text="局域网手机遥控", bg=desktop.BG, fg=desktop.TEXT, font=("Segoe UI Semibold", 16)).pack(anchor="w", padx=20, pady=(18, 10))
        urls = self.remote_server.urls() if self.remote_server else []
        address = "\n".join(urls) if urls else "未找到可用局域网 IPv4 地址"
        tk.Label(win, text=address, bg=desktop.PANEL2, fg=desktop.TEXT, justify="left", anchor="w", padx=12, pady=10).pack(fill="x", padx=20)
        pin_var = tk.StringVar(value=str(cfg.get("pin", "")))
        enabled_var = tk.BooleanVar(value=bool(cfg.get("enabled", True)))
        port_var = tk.IntVar(value=int(cfg.get("port", 8765)))
        row = tk.Frame(win, bg=desktop.BG); row.pack(fill="x", padx=20, pady=(14, 6))
        tk.Label(row, text="配对 PIN", bg=desktop.BG, fg=desktop.MUTED).pack(side="left")
        tk.Label(row, textvariable=pin_var, bg=desktop.BG, fg=desktop.TEXT, font=("Consolas", 18, "bold")).pack(side="right")
        port_row = tk.Frame(win, bg=desktop.BG); port_row.pack(fill="x", padx=20, pady=6)
        tk.Label(port_row, text="端口", bg=desktop.BG, fg=desktop.MUTED).pack(side="left")
        ttk.Spinbox(port_row, from_=1024, to=65535, textvariable=port_var, width=9).pack(side="right")
        ttk.Checkbutton(win, text="启用局域网遥控服务", variable=enabled_var).pack(anchor="w", padx=20, pady=8)
        status_var = tk.StringVar(value="")
        tk.Label(win, textvariable=status_var, bg=desktop.BG, fg=desktop.MUTED).pack(anchor="w", padx=20)
        buttons = tk.Frame(win, bg=desktop.BG); buttons.pack(fill="x", padx=20, pady=14)

        def apply_config():
            port = max(1024, min(65535, int(port_var.get())))
            cfg.update(enabled=bool(enabled_var.get()), port=port, pin=pin_var.get())
            self.settings_store.save()
            if cfg["enabled"]: self.remote_server.restart(pin=cfg["pin"], port=port)
            else: self.remote_server.stop()
            refresh_status()

        def regenerate():
            pin = f"{secrets.randbelow(1_000_000):06d}"; pin_var.set(pin); cfg["pin"] = pin; self.settings_store.save()
            if cfg.get("enabled", True): self.remote_server.restart(pin=pin, port=int(cfg.get("port", 8765)))
            refresh_status()

        def copy_info():
            url = (self.remote_server.urls() or [""])[0]
            self.clipboard_clear(); self.clipboard_append(f"{url}\nPIN: {pin_var.get()}"); self.update_idletasks()

        def refresh_status():
            if not win.winfo_exists(): return
            state = "运行中" if self.remote_server.running else "已停止"
            if self.remote_server.error: state += f" · {self.remote_server.error}"
            status_var.set(f"服务：{state} · 已连接客户端 {self.remote_server.client_count}")
            win.after(800, refresh_status)

        ttk.Button(buttons, text="应用", style="Accent.TButton", command=apply_config).pack(side="left", expand=True, fill="x")
        ttk.Button(buttons, text="复制地址和 PIN", command=copy_info).pack(side="left", expand=True, fill="x", padx=5)
        ttk.Button(buttons, text="更换 PIN", command=regenerate).pack(side="left", expand=True, fill="x")
        tk.Label(win, text="手机与电脑需在同一局域网；Windows 防火墙首次提示时允许专用网络访问。", bg=desktop.BG, fg=desktop.MUTED, wraplength=455, justify="left").pack(anchor="w", padx=20)
        refresh_status()

    def _restart_admin(self):
        try:
            if desktop.FROZEN:
                arguments = "--admin-restart"
            else:
                arguments = f'"{Path(__file__).resolve()}" --admin-restart'
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, arguments, str(desktop.ROOT), 1)
            if result > 32: self._close()
            else: messagebox.showerror("启动失败", f"无法获取管理员权限（代码 {result}）")
        except Exception as exc:
            messagebox.showerror("启动失败", str(exc))

    def _close(self):
        if self._closing: return
        if self.remote_server:
            try: self.remote_server.stop()
            except Exception: logging.debug("Remote server stop failed", exc_info=True)
        if self.system_media:
            try: self.system_media.stop()
            except Exception: logging.debug("Media bridge stop failed", exc_info=True)
        super()._close()


def self_test():
    for model in desktop.MODELS:
        addresses = [((0xB0 if model.address_kind == "legacy" and xy[1] == 0 else 0x90), model.address(*xy)) for xy in model.pads]
        if len(addresses) != len(set(addresses)):
            raise RuntimeError(f"Duplicate MIDI addresses: {model.name}")
    if len(desktop.clock_frame(desktop.datetime.now(), 0, (1, 2, 3), (4, 5, 6))) != 80:
        raise RuntimeError("Frame renderer failed")


def main():
    desktop.os.chdir(desktop.ROOT)
    if "--self-test" in sys.argv:
        self_test(); return 0
    if not desktop._single_instance(): return 0
    def _thread_error(args):
        logging.error("Background thread failed", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = _thread_error
    app = RemoteLaunchpadStudio()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
