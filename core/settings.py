from __future__ import annotations
import copy
import json
from pathlib import Path
import threading
import time


AUDIO_DETAIL_DEFAULTS = {
    "freq_min": 40, "freq_max": 16000, "loud_min": -55, "loud_max": -6,
    "sensitivity": 1.0, "threshold": .012, "speed": 1.0, "spread": 1.0,
}
VIDEO_DETAIL_DEFAULTS = {
    "fps": 20, "saturation": 1.25, "contrast": 1.0, "gamma": 1.0,
    "edge_threshold": 70, "effect": "原色视频",
}

DEFAULT = {
    "theme": "霓虹",
    "brightness": 85,
    "custom_color": "#7c5cff",
    "midi_in": "Launchpad MK2",
    "midi_out": "Launchpad MK2",
    "macros": {},
    "video_playlist": [],
    "audio_playlist": [],
    "launchpad_model": "auto",
    "detail_params": {
        "music": {**AUDIO_DETAIL_DEFAULTS, "style": "频谱", "volume": 85, "rate": "1.00×", "loop": "列表循环"},
        "live": {**AUDIO_DETAIL_DEFAULTS, "style": "星云"},
        "video": {**VIDEO_DETAIL_DEFAULTS, "rate": "1.00×", "loop": "列表循环"},
    },
    "presets": {"audio": {}, "video": {}},
    "recent_presets": {"music": [], "live": [], "video": []},
    "utilities": {"selected": "数字时钟", "weather_city": "北京", "focus_minutes": 25,
                  "snake_high_score": 0, "mole_high_score": 0,
                  "snake_difficulty": "简单", "mole_difficulty": "简单",
                  "rhythm_path": "", "rhythm_difficulty": "普通", "rhythm_speed": 3,
                  "rhythm_lanes": 6, "waterfall_high_score": 0, "maimai_high_score": 0},
    "macro_control_enabled": False,
    "live_device": "",
}


class Settings:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.data = copy.deepcopy(DEFAULT)
        self.load()

    def load(self):
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            self.data.update(loaded)
            # Merge nested defaults so older settings files migrate safely.
            details = self.data.setdefault("detail_params", {})
            for mode, defaults in DEFAULT["detail_params"].items():
                details[mode] = {**defaults, **details.get(mode, {})}
            for group in ("presets", "recent_presets"):
                merged = copy.deepcopy(DEFAULT[group]); merged.update(self.data.get(group, {}))
                self.data[group] = merged
            self.data["utilities"] = {**DEFAULT["utilities"], **self.data.get("utilities", {})}
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            # Preserve a damaged file for diagnosis instead of silently destroying it.
            try:self.path.replace(self.path.with_name(f"{self.path.stem}.corrupt-{int(time.time())}{self.path.suffix}"))
            except OSError:pass
        except OSError:
            pass

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.path)
