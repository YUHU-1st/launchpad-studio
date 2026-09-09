from __future__ import annotations
import shutil
import subprocess
import time
import psutil
from .launchpad import ALL_PADS
from .temperature import TemperatureMonitor
from pathlib import Path


PALETTES = {
    "霓虹": ((0, 245, 255), (255, 30, 210)),
    "海洋": ((0, 90, 255), (0, 255, 180)),
    "日落": ((255, 40, 90), (255, 190, 0)),
    "森林": ((20, 120, 50), (180, 255, 60)),
    "单色": ((55, 55, 70), (245, 245, 255)),
}


def mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * max(0, min(1, t))) for i in range(3))


class PerformanceMonitor:
    def __init__(self):
        psutil.cpu_percent(None)
        self.last_net = psutil.net_io_counters()
        self.last_disk = psutil.disk_io_counters()
        self.last_time = time.monotonic()
        self.temperature = TemperatureMonitor(Path(__file__).resolve().parents[1])

    def sample(self):
        now = time.monotonic()
        dt = max(.1, now - self.last_time)
        net = psutil.net_io_counters()
        disk = psutil.disk_io_counters()
        cpu = psutil.cpu_percent(None)
        per_cpu = psutil.cpu_percent(None, percpu=True)
        memory = psutil.virtual_memory().percent
        try:disk_used = psutil.disk_usage("C:\\").percent
        except OSError:disk_used = 0.0
        net_rate = 0.0 if net is None or self.last_net is None else ((net.bytes_sent + net.bytes_recv) - (self.last_net.bytes_sent + self.last_net.bytes_recv)) / dt
        disk_rate = 0.0 if disk is None or self.last_disk is None else ((disk.read_bytes + disk.write_bytes) - (self.last_disk.read_bytes + self.last_disk.write_bytes)) / dt
        self.last_net, self.last_disk, self.last_time = net, disk, now
        gpu = self._gpu()
        temperatures = self.temperature.sample()
        return {"CPU": cpu, "RAM": memory, "磁盘": disk_used, "GPU": gpu,
                "网络 MB/s": net_rate / 1048576, "磁盘 MB/s": disk_rate / 1048576,
                "cores": per_cpu, "temperatures": temperatures}

    def _gpu(self):
        if not shutil.which("nvidia-smi"):
            return None
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.check_output(["nvidia-smi", "--query-gpu=utilization.gpu",
                                           "--format=csv,noheader,nounits"], text=True,
                                          timeout=.8, creationflags=flags)
            return float(out.splitlines()[0])
        except Exception:
            return None

    def frame(self, stats, palette="霓虹", brightness=1.0):
        low, high = PALETTES.get(palette, PALETTES["霓虹"])
        frame = {xy: (0, 0, 0) for xy in ALL_PADS}
        metrics = [stats["CPU"], stats["RAM"], stats["磁盘"], stats["GPU"] or 0,
                   min(100, stats["网络 MB/s"] * 8), min(100, stats["磁盘 MB/s"] * 4),
                   sum(stats["cores"][::2]) / max(1, len(stats["cores"][::2])),
                   max(stats["cores"] or [0])]
        for x, value in enumerate(metrics):
            height = round(value / 100 * 8)
            for iy in range(8):
                y = 8 - iy
                if iy < height:
                    rgb = mix(low, high, iy / 7)
                    frame[(x, y)] = tuple(round(c * brightness) for c in rgb)
        # Top: metric markers; right: a CPU/RAM blended meter.
        for x in range(8):
            frame[(x, 0)] = tuple(round(c * brightness * .55) for c in mix(low, high, x / 7))
        known_temps = [v for k, v in stats.get("temperatures", {}).items()
                       if k in ("CPU", "GPU", "主板", "存储") and isinstance(v, (int, float))]
        # Right controls become a thermal bar (30–100 °C). If no sensor is
        # available, keep the previous CPU/RAM activity fallback.
        thermal = max(known_temps) if known_temps else 30 + (stats["CPU"] + stats["RAM"]) * .35
        heat = max(0, min(100, (thermal - 30) / 70 * 100))
        for y in range(1, 9):
            if 9 - y <= heat / 100 * 8:
                t = (8-y)/7
                heat_color = mix((0, 180, 255), (255, 30, 20), t)
                frame[(8, y)] = tuple(round(c * brightness) for c in heat_color)
        return frame
