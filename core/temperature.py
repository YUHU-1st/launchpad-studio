from __future__ import annotations
import json
import ctypes
from pathlib import Path
import shutil
import subprocess
import threading
import time


class TemperatureMonitor:
    """Crash-isolated sensor polling with NVIDIA fallback.

    LibreHardwareMonitor runs out-of-process because low-level motherboard drivers
    must never be allowed to take down the UI or MIDI threads.
    """
    def __init__(self, root: Path):
        self.helper = root / "tools" / "TemperatureHelper" / "publish" / "TemperatureHelper.exe"
        self.values = {"CPU": None, "GPU": None, "主板": None, "存储": None, "sensors": []}
        self.last_poll = 0.0
        self.polling = False
        self.lock = threading.Lock()

    def sample(self):
        now = time.monotonic()
        if not self.polling and now - self.last_poll > 4.0:
            self.polling = True
            threading.Thread(target=self._poll, daemon=True).start()
        with self.lock:
            return dict(self.values)

    def _poll(self):
        fresh = None
        try:
            if self.helper.exists():
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                raw = subprocess.check_output([str(self.helper)], text=True, encoding="utf-8",
                                              errors="replace", timeout=8, creationflags=flags)
                fresh = json.loads(raw.strip().splitlines()[-1])
        except Exception:
            fresh = None
        if fresh is None:
            fresh = {"CPU": None, "GPU": None, "主板": None, "存储": None, "sensors": []}
        if fresh.get("GPU") is None and shutil.which("nvidia-smi"):
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                value = subprocess.check_output(["nvidia-smi", "--query-gpu=temperature.gpu",
                                                 "--format=csv,noheader,nounits"], text=True,
                                                timeout=1.2, creationflags=flags)
                fresh["GPU"] = float(value.splitlines()[0])
            except Exception:
                pass
        # Lenovo gaming laptops expose authoritative CPU/GPU package sensors
        # through an OEM WMI method, but Windows only permits it when elevated.
        try:
            if ctypes.windll.shell32.IsUserAnAdmin():
                script = ("$x=Get-CimInstance -Namespace root\\wmi -ClassName LENOVO_GAMEZONE_DATA;"
                          "$c=(Invoke-CimMethod -InputObject $x -MethodName GetCPUTemp).Data;"
                          "$g=(Invoke-CimMethod -InputObject $x -MethodName GetGPUTemp).Data;"
                          "[pscustomobject]@{CPU=$c;GPU=$g}|ConvertTo-Json -Compress")
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                raw = subprocess.check_output(["powershell", "-NoProfile", "-Command", script],
                                              text=True, timeout=3, creationflags=flags)
                oem = json.loads(raw)
                for key in ("CPU", "GPU"):
                    value = oem.get(key)
                    if isinstance(value, (int, float)) and 1 <= value <= 150:
                        fresh[key] = value
        except Exception:
            pass
        with self.lock:
            self.values = fresh
            self.last_poll = time.monotonic()
            self.polling = False
