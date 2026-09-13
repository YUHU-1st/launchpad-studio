from __future__ import annotations

import ctypes
import logging
from pathlib import Path
import sys
import threading
from tkinter import messagebox

import app as desktop
from launchpad_remote import RemoteLaunchpadStudio, self_test


VISUAL_RANGES = {
    "freq_min": (20.0, 1000.0),
    "freq_max": (1000.0, 22000.0),
    "loud_min": (-80.0, -20.0),
    "loud_max": (-30.0, 0.0),
    "sensitivity": (0.1, 4.0),
    "threshold": (0.0, 0.2),
    "speed": (0.2, 3.0),
    "spread": (0.3, 2.5),
}
VIDEO_RANGES = {
    "fps": (5.0, 30.0),
    "saturation": (0.0, 2.0),
    "contrast": (0.2, 2.5),
    "gamma": (0.25, 2.5),
    "edge_threshold": (10.0, 180.0),
}


class LaunchpadStudioRemote(RemoteLaunchpadStudio):
    """Production remote app with synchronized desktop/mobile parameter state."""

    @staticmethod
    def _clamp(value, limits):
        lo, hi = limits
        return max(lo, min(hi, float(value)))

    def _validated_detail(self, mode: str, updates: dict) -> dict:
        clean = {}
        for key, value in dict(updates or {}).items():
            key = str(key)
            ranges = VIDEO_RANGES if mode == "video" else VISUAL_RANGES
            if key in ranges:
                number = self._clamp(value, ranges[key])
                clean[key] = int(round(number)) if key in {"fps", "edge_threshold"} else number
            elif key == "volume" and mode == "music":
                clean[key] = self._clamp(value, (0.0, 100.0))
            elif key in {"rate", "loop", "effect", "style"}:
                clean[key] = str(value)
        return clean

    def _sync_detail_vars(self, mode: str, detail: dict):
        if mode == "video":
            for key, var in getattr(self, "video_vars", {}).items():
                if key in detail:
                    var.set(float(detail[key]))
            if hasattr(self, "video_fps") and "fps" in detail:
                self.video_fps.set(int(detail["fps"]))
            if hasattr(self, "video_effect") and "effect" in detail:
                self.video_effect.set(str(detail["effect"]))
            if hasattr(self, "video_rate") and "rate" in detail:
                self.video_rate.set(str(detail["rate"]))
            if hasattr(self, "video_loop") and "loop" in detail:
                self.video_loop.set(str(detail["loop"]))
            return
        visual_vars = getattr(self, f"{mode}_visual_vars", {})
        for key, var in visual_vars.items():
            if key in detail:
                var.set(float(detail[key]))
        style = getattr(self, f"{mode}_style", None)
        if style is not None and "style" in detail:
            style.set(str(detail["style"]))
        if mode == "music":
            if hasattr(self, "audio_volume") and "volume" in detail:
                self.audio_volume.set(float(detail["volume"]))
            if hasattr(self, "audio_rate") and "rate" in detail:
                self.audio_rate.set(str(detail["rate"]))
            if hasattr(self, "audio_loop") and "loop" in detail:
                self.audio_loop.set(str(detail["loop"]))

    def _set_detail(self, mode: str, updates: dict):
        clean = self._validated_detail(mode, updates)
        if not clean:
            return
        super()._set_detail(mode, clean)
        detail = dict(self.settings_store.data["detail_params"][mode])
        self._sync_detail_vars(mode, detail)

    def _restart_admin(self):
        try:
            if desktop.FROZEN:
                arguments = "--admin-restart"
            else:
                arguments = f'"{Path(__file__).resolve()}" --admin-restart'
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, arguments, str(desktop.ROOT), 1
            )
            if result > 32:
                self._close()
            else:
                messagebox.showerror("启动失败", f"无法获取管理员权限（代码 {result}）")
        except Exception as exc:
            messagebox.showerror("启动失败", str(exc))


def main():
    desktop.os.chdir(desktop.ROOT)
    if "--self-test" in sys.argv:
        self_test()
        return 0
    if not desktop._single_instance():
        return 0

    def _thread_error(args):
        logging.error(
            "Background thread failed",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_error
    application = LaunchpadStudioRemote()
    application.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
