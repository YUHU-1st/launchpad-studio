from __future__ import annotations
import threading
import time
import cv2
import numpy as np
from .launchpad import ALL_PADS


class VideoPlayer:
    def __init__(self, on_frame, on_status=None, on_progress=None, on_finished=None):
        self.on_frame = on_frame
        self.on_status = on_status or (lambda _x: None)
        self.on_progress = on_progress or (lambda _p, _d: None)
        self.on_finished = on_finished or (lambda: None)
        self.stop_event = threading.Event()
        self.thread = None
        self.lock = threading.RLock()
        self.paused = False
        self.rate = 1.0
        self.position = 0.0
        self.duration = 0.0
        self.seek_request = None
        self.effect = "原色视频"
        self.params = {}

    def start(self, path, fps_limit=24, brightness=1.0, saturation=1.0,
              rate=1.0, start_at=0.0, effect="原色视频", params=None):
        self.stop()
        self.stop_event.clear()
        with self.lock:
            self.paused = False; self.rate = float(rate); self.position = float(start_at)
            self.effect = effect; self.params = dict(params or {})
            self.params.setdefault("saturation", saturation)
            self.params.setdefault("brightness", brightness)
        self.thread = threading.Thread(target=self._run, args=(path, fps_limit), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        thread = self.thread
        if thread and thread is not threading.current_thread(): thread.join(timeout=1.5)
        self.thread = None

    def pause_toggle(self):
        with self.lock:
            self.paused = not self.paused
            return self.paused

    def seek(self, seconds):
        with self.lock: self.seek_request = max(0.0, min(float(seconds), self.duration))

    def set_rate(self, rate):
        with self.lock: self.rate = max(.25, min(3.0, float(rate)))

    def set_effect(self, effect=None, params=None):
        with self.lock:
            if effect is not None: self.effect = effect
            if params is not None: self.params.update(params)

    def _filter(self, image, effect, params):
        small = cv2.resize(image, (8, 8), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32)
        saturation = float(params.get("saturation", 1.0))
        contrast = float(params.get("contrast", 1.0))
        brightness = float(params.get("brightness", 1.0))
        gamma = max(.15, float(params.get("gamma", 1.0)))
        gray = rgb.mean(axis=2, keepdims=True)
        if effect == "亮度热图":
            heat = cv2.applyColorMap(gray[:,:,0].astype(np.uint8), cv2.COLORMAP_TURBO)
            rgb = cv2.cvtColor(heat, cv2.COLOR_BGR2RGB).astype(np.float32)
        elif effect == "边缘轮廓":
            t = int(params.get("edge_threshold", 70))
            edge = cv2.Canny(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), t, t*2)
            rgb = np.stack([edge, edge*.35, 255-edge], axis=2).astype(np.float32)
        elif effect == "单色辉光":
            rgb = (gray/255) * np.asarray(params.get("tint", (124,92,255)), dtype=np.float32)
        elif effect == "镜像万花筒":
            q = rgb[:4,:4]
            rgb = np.concatenate([np.concatenate([q,q[:,::-1]],1),
                                  np.concatenate([q[::-1],q[::-1,::-1]],1)],0)
        elif effect == "像素故障":
            shift = int(time.monotonic()*8)%8
            rgb[::2] = np.roll(rgb[::2],shift,axis=1); rgb[:,:,0] = np.roll(rgb[:,:,0],1,axis=1)
        gray = rgb.mean(axis=2,keepdims=True)
        rgb = gray+(rgb-gray)*saturation
        rgb = (rgb-127.5)*contrast+127.5
        rgb = np.power(np.clip(rgb/255,0,1),1/gamma)*255*brightness
        return np.clip(rgb,0,255).astype(np.uint8)

    def _run(self, path, fps_limit):
        cap = cv2.VideoCapture(path)
        if not cap.isOpened(): self.on_status("无法打开视频"); return
        source_fps = cap.get(cv2.CAP_PROP_FPS) or 24
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        self.duration = total_frames/source_fps if total_frames else 0
        cap.set(cv2.CAP_PROP_POS_MSEC,self.position*1000)
        fps = min(max(1,fps_limit),source_fps); next_time=time.monotonic(); natural_end=False; skip_accum=0.0
        self.on_status(f"播放中 · {source_fps:.1f} FPS → {fps:.1f} FPS")
        while not self.stop_event.is_set():
            with self.lock:
                paused,rate=self.paused,self.rate; seek=self.seek_request; self.seek_request=None
                effect,params=self.effect,dict(self.params)
            if seek is not None:
                cap.set(cv2.CAP_PROP_POS_MSEC,seek*1000); self.position=seek; next_time=time.monotonic()
            if paused:
                self.stop_event.wait(.04); next_time=time.monotonic(); continue
            ok,image=cap.read()
            if not ok: natural_end=True; break
            advance = source_fps/fps*rate
            if advance >= 1:
                skip_accum += advance-1
                grabs=int(skip_accum); skip_accum-=grabs
                for _ in range(grabs): cap.grab()
            rgb=self._filter(image,effect,params); frame={xy:(0,0,0) for xy in ALL_PADS}
            for y in range(8):
                for x in range(8): frame[(x,y+1)]=tuple(int(v) for v in rgb[y,x])
            for x in range(8): frame[(x,0)]=tuple(int(v) for v in rgb[:,x].mean(axis=0))
            for y in range(8): frame[(8,y+1)]=tuple(int(v) for v in rgb[y].mean(axis=0))
            self.position=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            self.on_frame(frame); self.on_progress(self.position,self.duration)
            next_time += 1/fps if advance>=1 else 1/(source_fps*max(.25,rate))
            self.stop_event.wait(max(0,next_time-time.monotonic()))
        cap.release()
        if natural_end and not self.stop_event.is_set(): self.on_finished()
        else: self.on_status("已停止")
