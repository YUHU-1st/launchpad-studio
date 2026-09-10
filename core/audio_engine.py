from __future__ import annotations
import colorsys
import math
import queue
import threading
import numpy as np
import soundfile as sf
import sounddevice as sd
try:
    import pyaudiowpatch as pyaudio
except ImportError:
    pyaudio = None
from .launchpad import ALL_PADS
from .performance import PALETTES, mix


def audio_devices():
    result = []
    if pyaudio is not None:
        try:
            with pyaudio.PyAudio() as pa:
                for dev in pa.get_loopback_device_info_generator():
                    result.append((f"loop:{dev['index']}", f"系统声音 · {dev['name']} · WASAPI Loopback"))
        except Exception:
            pass
    try:
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                host = sd.query_hostapis(dev["hostapi"])["name"]
                result.append((f"input:{idx}", f"麦克风/输入 · {dev['name']} · {host}"))
    except Exception:
        pass
    return result


class AudioAnalysis:
    def __init__(self, path):
        data, sr = sf.read(path, always_2d=True, dtype="float32")
        self.audio = data
        self.data = data.mean(axis=1)
        self.sr = sr
        self.duration = len(self.data) / sr
        self.bpm, self.energy, self.brightness = self._analyse()
        self.mood = self._mood()
        self.genre = self._genre()

    def _analyse(self):
        if not len(self.data):
            return 120, 0, 0
        hop = 512
        usable = self.data[: min(len(self.data), self.sr * 180)]
        count = len(usable) // hop
        chunks = usable[:count * hop].reshape(count, hop)
        rms = np.sqrt(np.mean(chunks * chunks, axis=1) + 1e-9)
        onset = np.maximum(0, np.diff(rms, prepend=rms[0]))
        onset -= onset.mean()
        corr = np.correlate(onset, onset, mode="full")[len(onset)-1:]
        min_lag = max(1, round(60 / 200 * self.sr / hop))
        max_lag = min(len(corr)-1, round(60 / 60 * self.sr / hop))
        lag = min_lag + int(np.argmax(corr[min_lag:max_lag+1])) if max_lag > min_lag else 1
        bpm = 60 * self.sr / (hop * lag)
        sample = usable[: min(len(usable), self.sr * 30)]
        spec = np.abs(np.fft.rfft(sample[::4]))
        freq = np.fft.rfftfreq(len(sample[::4]), 4 / self.sr)
        centroid = float((spec * freq).sum() / max(1e-9, spec.sum()))
        return round(float(bpm)), float(np.clip(rms.mean() * 5, 0, 1)), float(np.clip(centroid / 5000, 0, 1))

    def _mood(self):
        if self.bpm > 140 and self.energy > .35:
            return "激昂"
        if self.bpm < 90 and self.brightness < .35:
            return "沉静"
        if self.brightness > .55:
            return "明亮"
        return "律动"

    def _genre(self):
        if self.bpm >= 145:
            return "高速电子 / 鼓打贝斯"
        if self.bpm >= 118 and self.energy >= .28:
            return "舞曲 / 电子"
        if self.bpm <= 92 and self.brightness < .42:
            return "氛围 / 慢拍"
        if self.brightness > .58:
            return "流行 / 明亮"
        return "律动 / 综合"

    def window(self, seconds, size=4096):
        i = max(0, min(len(self.data), round(seconds * self.sr)))
        return self.data[i:i+size]


def reactive_frame(samples, sr, style="频谱", palette="霓虹", brightness=1.0, tick=0, params=None):
    params = params or {}
    freq_min = max(20.0, float(params.get("freq_min", 40)))
    freq_max = min(sr / 2, max(freq_min + 10, float(params.get("freq_max", 16000))))
    sensitivity = max(.05, float(params.get("sensitivity", 1.0)))
    threshold = max(0.0, float(params.get("threshold", .012)))
    loud_min = float(params.get("loud_min", -55))
    loud_max = max(loud_min + 1, float(params.get("loud_max", -6)))
    speed = max(.05, float(params.get("speed", 1.0)))
    spread = max(.1, float(params.get("spread", 1.0)))
    low, high = PALETTES.get(palette, PALETTES["霓虹"])
    frame = {xy: (0, 0, 0) for xy in ALL_PADS}
    if samples is None or len(samples) < 32:
        return frame
    samples = np.asarray(samples, dtype=np.float32)
    # Some WASAPI drivers briefly return non-finite/denormal data while a
    # loopback stream is starting or stopping. Sanitize it before FFT/RMS.
    samples = np.clip(np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0), -4.0, 4.0)
    rms = float(np.sqrt(np.mean(samples * samples) + 1e-8))
    rms_db = 20 * math.log10(max(1e-8, rms))
    loudness = float(np.clip((rms_db - loud_min) / (loud_max - loud_min), 0, 1))
    windowed = samples * np.hanning(len(samples))
    spec = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(samples), 1 / sr)
    edges = np.geomspace(freq_min, freq_max, 9)
    levels = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        band = spec[(freqs >= lo) & (freqs < hi)]
        levels.append(np.log1p(band.mean()) if len(band) else 0)
    levels = np.asarray(levels)
    levels = np.clip(levels / max(.15, levels.max()) * sensitivity, 0, 1)
    if rms < threshold:
        levels *= 0
        loudness = 0
    phase = tick * speed
    if style == "频谱":
        for x, level in enumerate(levels):
            h = round(level * 8)
            for i in range(h):
                frame[(x, 8-i)] = tuple(round(c*brightness) for c in mix(low, high, i/7))
    elif style == "对称频谱":
        mirror = np.r_[levels[:4], levels[3::-1]]
        for x, level in enumerate(mirror):
            h = round(level * 4)
            for i in range(h):
                color = tuple(round(c*brightness) for c in mix(low, high, i/3))
                frame[(x, 4-i)] = color; frame[(x, 5+i)] = color
    elif style == "波形":
        points = np.array_split(samples, 8)
        wave = [float(np.mean(p)) * sensitivity for p in points]
        for x, value in enumerate(wave):
            center = int(np.clip(round(4.5 - value * 18), 1, 8))
            for y in range(max(1, center-1), min(8, center+1)+1):
                power = 1 if y == center else .35
                frame[(x,y)] = tuple(round(c*brightness*power) for c in mix(low, high, x/7))
    elif style == "涟漪":
        radius = (phase * .18) % 6
        for y in range(1, 9):
            for x in range(8):
                d = math.hypot(x-3.5, y-4.5)
                power = max(0, 1-abs(d-radius)/(1.6*spread)) * loudness
                frame[(x,y)] = tuple(round(c*brightness*power) for c in mix(low, high, d/6))
    elif style == "脉冲":
        power = loudness
        for y in range(1, 9):
            for x in range(8):
                d = max(abs(x-3.5), abs(y-4.5))
                on = d <= .7 + power*4
                if on:
                    frame[(x,y)] = tuple(round(c*brightness*power) for c in mix(low, high, d/4))
    elif style == "星云":
        for y in range(1,9):
            for x in range(8):
                hue = ((x+y)/16 + phase*.012 + levels[x]*.25*spread) % 1
                rgb = colorsys.hsv_to_rgb(hue, .85, min(1, .06+loudness*.65+levels[x]*.35))
                frame[(x,y)] = tuple(round(v*255*brightness) for v in rgb)
    elif style == "雨幕":
        rng = np.random.default_rng(int(phase * 2))
        for x in range(8):
            head = int((phase * (.12 + levels[x]*.35) + x*1.7) % 11) - 2
            for y in range(1,9):
                trail = y - head
                power = max(0, 1-abs(trail)/(2.2*spread)) * (.25+levels[x]*.75)
                if rng.random() < .04*loudness: power = max(power, loudness)
                frame[(x,y)] = tuple(round(c*brightness*power) for c in mix(low, high, x/7))
    elif style == "火焰":
        rng = np.random.default_rng(int(phase))
        for y in range(1,9):
            base = (y-1)/7
            for x in range(8):
                flicker = .7 + .3*rng.random()
                power = max(0, loudness*1.25 - base/(1.2*spread)) * flicker
                flame = mix((255,25,0),(255,220,20),max(0,1-base))
                frame[(x,9-y)] = tuple(round(c*brightness*min(1,power)) for c in flame)
    elif style == "隧道":
        for y in range(1,9):
            for x in range(8):
                ring = max(abs(x-3.5),abs(y-4.5))
                power = max(0, math.sin((ring*1.8-phase*.18)*math.pi)*.5+.5) * loudness
                frame[(x,y)] = tuple(round(c*brightness*power) for c in mix(low,high,ring/4))
    else:  # 棋盘
        for y in range(1,9):
            for x in range(8):
                power = loudness if (x+y+int(phase*.1))%2==0 else levels[x]*.25
                frame[(x,y)] = tuple(round(c*brightness*power) for c in mix(low,high,(x+y)/15))
    edge = tuple(round(c*brightness*loudness) for c in high)
    for x in range(8): frame[(x,0)] = edge if x <= round(levels.mean()*7) else (0,0,0)
    for y in range(1,9): frame[(8,y)] = tuple(round(c*brightness*levels[8-y]) for c in low)
    return frame


class MusicShow:
    def __init__(self, on_frame, on_status=None, on_progress=None, on_finished=None, emit_frames=True):
        self.on_frame = on_frame
        self.on_status = on_status or (lambda _s: None)
        self.on_progress = on_progress or (lambda _p, _d: None)
        self.on_finished = on_finished or (lambda: None)
        self.emit_frames = emit_frames
        self.analysis = None
        self.stop_event = threading.Event()
        self.stream = None
        self.worker = None
        self.cursor = 0.0
        self.rate = 1.0
        self.volume = .85
        self.paused = False
        self.ended = False
        self.loop_track = False
        self.lock = threading.RLock()
        self.visual = {"style":"频谱", "palette":"霓虹", "brightness":1.0, "params":{}}

    def analyse(self, path):
        self.analysis = AudioAnalysis(path)
        self.path = str(path)
        return self.analysis

    def start(self, path, style, palette, brightness, params=None, start_at=0.0, rate=1.0, loop_track=False):
        self.stop()
        if self.analysis is None or getattr(self, "path", None) != str(path):
            self.analyse(path)
        self.path = str(path)
        self.stop_event.clear()
        self.ended = False; self.paused = False; self.rate = float(rate); self.loop_track = loop_track
        self.cursor = max(0.0, min(self.analysis.duration, float(start_at))) * self.analysis.sr
        self.visual = {"style":style, "palette":palette, "brightness":brightness, "params":params or {}}
        channels = self.analysis.audio.shape[1]
        self.stream = sd.OutputStream(samplerate=self.analysis.sr, channels=channels,
                                      dtype="float32", blocksize=1024, latency="low",
                                      callback=self._audio_callback)
        self.stream.start()
        self.worker = threading.Thread(target=self._run_visual, daemon=True)
        self.worker.start()
        self.on_status("灯光秀播放中")

    def _audio_callback(self, outdata, frames, _time_info, _status):
        with self.lock:
            if self.stop_event.is_set() or self.paused:
                outdata.fill(0); return
            audio = self.analysis.audio
            if not len(audio):
                outdata.fill(0); self.ended = True; return
            positions = self.cursor + np.arange(frames, dtype=np.float64) * self.rate
            if positions[-1] >= len(audio):
                if self.loop_track and len(audio):
                    positions %= len(audio)
                    self.cursor = float((positions[-1] + self.rate) % len(audio))
                    valid = np.ones(frames, dtype=bool)
                else:
                    valid = positions < len(audio)
                    positions = np.clip(positions, 0, max(0, len(audio)-1))
                    self.cursor = float(len(audio)); self.ended = True
                    if not valid.all():
                        # Interpolate valid samples, then silence the tail.
                        pass
            else:
                valid = np.ones(frames, dtype=bool)
                self.cursor = float(positions[-1] + self.rate)
            left = np.floor(positions).astype(np.int64)
            right = np.minimum(left + 1, len(audio)-1)
            frac = (positions-left)[:,None]
            rendered = audio[left]*(1-frac) + audio[right]*frac
            outdata[:] = rendered * self.volume
            if not valid.all(): outdata[~valid] = 0

    def _run_visual(self):
        tick = 0
        natural_end = False
        while not self.stop_event.is_set():
            with self.lock:
                pos = self.cursor / self.analysis.sr
                ended = self.ended
                visual = dict(self.visual)
            self.on_progress(pos, self.analysis.duration)
            if self.emit_frames:
                self.on_frame(reactive_frame(self.analysis.window(pos), self.analysis.sr,
                              visual["style"], visual["palette"], visual["brightness"], tick, visual["params"]))
            tick += 1
            if ended:
                natural_end = True; break
            self.stop_event.wait(1/30)
        if natural_end and not self.stop_event.is_set():
            self.on_finished()

    def pause_toggle(self):
        with self.lock:
            self.paused = not self.paused
            return self.paused

    def seek(self, seconds):
        with self.lock:
            if self.analysis:
                self.cursor = max(0, min(float(seconds), self.analysis.duration)) * self.analysis.sr
                self.ended = False

    def set_rate(self, rate):
        with self.lock: self.rate = max(.25, min(3.0, float(rate)))

    def set_volume(self, volume):
        with self.lock: self.volume = max(0.0, min(1.0, float(volume)))

    def set_visual(self, style=None, palette=None, brightness=None, params=None):
        with self.lock:
            if style is not None: self.visual["style"] = style
            if palette is not None: self.visual["palette"] = palette
            if brightness is not None: self.visual["brightness"] = brightness
            if params is not None: self.visual["params"] = params

    def stop(self):
        self.stop_event.set()
        if self.stream:
            try: self.stream.stop()
            except Exception: pass
        worker = self.worker
        if worker and worker is not threading.current_thread(): worker.join(timeout=1.5)
        self.worker = None
        if self.stream:
            try: self.stream.close()
            except Exception: pass
            self.stream = None


class LiveAudio:
    def __init__(self, on_frame, on_status=None):
        self.on_frame = on_frame
        self.on_status = on_status or (lambda _s: None)
        self.stop_event = threading.Event()
        self.stream = None
        self.q = queue.Queue(maxsize=3)
        self.pa = None
        self.worker = None
        self.backend = None
        self.visual = {"style":"星云", "palette":"霓虹", "brightness":1.0, "params":{}}

    def start(self, device, style, palette, brightness, params=None):
        self.stop()
        if self.worker and self.worker.is_alive():
            raise RuntimeError("上一个音频设备仍在退出，请稍后再试")
        self.stop_event.clear()
        self.q = queue.Queue(maxsize=3)
        self.visual = {"style":style, "palette":palette, "brightness":brightness, "params":params or {}}
        if isinstance(device, str) and device.startswith("loop:"):
            return self._start_loopback(int(device.split(":", 1)[1]))
        if isinstance(device, str) and device.startswith("input:"):
            device = int(device.split(":", 1)[1])
        def callback(indata, _frames, _time, status):
            try:
                if self.q.full(): self.q.get_nowait()
                self.q.put_nowait(indata.mean(axis=1).copy())
            except queue.Empty: pass
        info = sd.query_devices(device, "input")
        sr = int(info["default_samplerate"])
        self.stream = sd.InputStream(device=device, channels=min(2, int(info["max_input_channels"])),
                                     samplerate=sr, blocksize=1024, latency="low", callback=callback)
        self.stream.start()
        self.backend = "sounddevice"
        self.worker = threading.Thread(target=self._run, args=(sr,), daemon=True)
        self.worker.start()
        self.on_status(f"实时拾音 · {sr} Hz")

    def _start_loopback(self, device):
        if pyaudio is None:
            raise RuntimeError("系统声音回采组件未安装")
        self.pa = pyaudio.PyAudio()
        info = self.pa.get_device_info_by_index(device)
        sr = int(info["defaultSampleRate"])
        channels = max(1, int(info["maxInputChannels"]))
        self.stream = self.pa.open(format=pyaudio.paFloat32, channels=channels, rate=sr,
                                   input=True, input_device_index=device, frames_per_buffer=1024)
        self.backend = "loopback"
        self.worker = threading.Thread(target=self._run_loopback,
                         args=(sr, channels), daemon=True)
        self.worker.start()
        self.on_status(f"系统声音回采中 · WASAPI · {sr} Hz")

    def _run_loopback(self, sr, channels):
        tick = 0
        while not self.stop_event.is_set():
            try:
                raw = self.stream.read(1024, exception_on_overflow=False)
                samples = np.frombuffer(raw, dtype=np.float32).reshape(-1, channels).mean(axis=1)
                v=self.visual
                self.on_frame(reactive_frame(samples, sr, v["style"], v["palette"], v["brightness"], tick, v["params"]))
                tick += 1
            except Exception as exc:
                self.on_status(f"系统声音回采错误：{exc}")
                break

    def _run(self, sr):
        tick = 0
        while not self.stop_event.is_set():
            try: samples = self.q.get(timeout=.2)
            except queue.Empty: continue
            v=self.visual
            self.on_frame(reactive_frame(samples, sr, v["style"], v["palette"], v["brightness"], tick, v["params"]))
            tick += 1

    def set_visual(self, style=None, palette=None, brightness=None, params=None):
        if style is not None: self.visual["style"] = style
        if palette is not None: self.visual["palette"] = palette
        if brightness is not None: self.visual["brightness"] = brightness
        if params is not None: self.visual["params"] = params

    def stop(self):
        self.stop_event.set()
        if self.stream:
            try:
                if self.backend == "loopback" and hasattr(self.stream, "stop_stream"):
                    self.stream.stop_stream()
                elif hasattr(self.stream, "stop"):
                    self.stream.stop()
            except Exception: pass
        # Never release WASAPI while a blocking read is still active. Doing so can
        # access freed memory inside AUDIOSES.DLL and terminate the whole process.
        worker = self.worker
        if worker and worker is not threading.current_thread():
            worker.join(timeout=2.5)
        if worker and worker.is_alive():
            self.on_status("音频设备正在安全退出，请稍候")
            return
        self.worker = None
        if self.stream:
            try: self.stream.close()
            except Exception: pass
            self.stream = None
        if self.pa:
            try: self.pa.terminate()
            except Exception: pass
            self.pa = None
        self.backend = None
