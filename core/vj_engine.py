from __future__ import annotations

from collections import deque
import math
import multiprocessing as mp
import queue
import threading
import time

import numpy as np

VJ_STYLES = ("自动编排", "霓虹隧道", "激光矩阵", "星际粒子", "分形星云", "几何万花筒", "液态铬金", "合成波日落", "暗黑科技")
VJ_ASPECTS = ("16:9", "21:9", "32:9", "4:3", "1:1", "9:16", "自定义")
VJ_FPS = (24, 25, 30, 50, 60)


def display_targets():
    from screeninfo import get_monitors
    return [{"id":m.name or str(i), "label":f"显示器 {i+1} · {m.width}×{m.height}"+(" · 主屏" if m.is_primary else ""),
             "x":m.x, "y":m.y, "width":m.width, "height":m.height} for i,m in enumerate(get_monitors())]


def validate_vj_config(raw):
    """Validate desktop/mobile settings at the user-input boundary."""
    cfg=dict(raw)
    if cfg["style"] not in VJ_STYLES or cfg["aspect"] not in VJ_ASPECTS:
        raise ValueError("VJ 风格或画幅无效")
    from .performance import PALETTES
    if cfg["palette"] not in (*PALETTES,"自动配色","自定义") or not isinstance(cfg["device"],str):
        raise ValueError("配色或音频输入无效")
    width,height=int(cfg["width"]),int(cfg["height"])
    if not 128<=width<=7680 or not 128<=height<=4320 or width*height>33_177_600:
        raise ValueError("分辨率范围为 128–7680 × 128–4320，最多 3300 万像素")
    if cfg["aspect"]!="自定义":
        a,b=map(int,cfg["aspect"].split(":"))
        if abs(width/height-a/b)/(a/b)>.015:raise ValueError("分辨率与所选画幅不一致，请调整高度或选择自定义")
    cfg.update(width=width,height=height,fps=int(cfg["fps"]))
    if cfg["fps"] not in VJ_FPS:raise ValueError("请选择支持的输出帧率")
    for key,lo,hi in (("sensitivity",.1,4),("threshold",0,.2),("speed",.1,3),("intensity",.1,2),("detail",.3,2),("scene_seconds",4,120)):
        value=float(cfg[key])
        if not math.isfinite(value) or not lo<=value<=hi:raise ValueError(f"{key} 超出可调范围")
        cfg[key]=value
    if not isinstance(cfg["screens"],list) or any(not isinstance(item,str) for item in cfg["screens"]):raise ValueError("投屏目标无效")
    if len(cfg["screens"])!=len(set(cfg["screens"])):raise ValueError("投屏目标不能重复")
    for key in ("preview","alpha","map_launchpad"):
        if not isinstance(cfg[key],bool):raise ValueError("VJ 开关参数必须为布尔值")
    if not cfg["preview"] and not cfg["screens"]:raise ValueError("请开启小窗口预览或至少选择一个投屏显示器")
    return cfg


class RealtimeMusicFeatures:
    """Streaming onsets/tempo, spectral bands and explicitly heuristic descriptors."""
    def __init__(self):
        self.lock=threading.Lock(); self.samples=np.zeros(4096,dtype=np.float32)
        self.envelope=deque(maxlen=700); self.onsets=deque(maxlen=32)
        self.elapsed=0.; self.last_tempo=0.; self.last_beat=-10.; self.last_sample=0.
        self.previous_rms=0.; self.energy=0.; self.bass=0.; self.mid=0.; self.treble=0.
        self.centroid=0.; self.bpm=0.; self.confidence=0.; self.beats=0
        self.band_levels=np.zeros(32,dtype=np.float32); self.flux_mean=.005; self.sr=0

    def feed(self,samples,sr,sensitivity=1.,threshold=.008):
        samples=np.clip(np.nan_to_num(np.asarray(samples,dtype=np.float32)), -4,4)
        if not len(samples):return
        dt=len(samples)/sr
        with self.lock:
            self.elapsed+=dt; self.last_sample=time.monotonic()
            if self.sr!=sr:self.samples.fill(0); self.sr=sr
            chunk=samples[-4096:]; self.samples=np.roll(self.samples,-len(chunk)); self.samples[-len(chunk):]=chunk
            rms=float(np.sqrt(np.mean(samples*samples))); active=rms>=threshold
            energy=float(np.clip((20*math.log10(max(rms,1e-8))+55)/49*sensitivity,0,1)) if active else 0.
            smooth=1-math.exp(-dt/.15); self.energy+=(energy-self.energy)*smooth
            spectrum=np.abs(np.fft.rfft(self.samples*np.hanning(4096)))
            freq=np.fft.rfftfreq(4096,1/sr)
            total=max(1e-8,float(spectrum.sum()))
            ratios=[float(spectrum[(freq>=lo)&(freq<hi)].sum())/total for lo,hi in ((30,250),(250,2500),(2500,sr/2))]
            self.bass,self.mid,self.treble=[r*self.energy for r in ratios]
            self.centroid=float((spectrum*freq).sum()/total) if active else 0.
            edges=np.geomspace(35,min(16000,sr/2),33)
            bands=np.array([float(spectrum[(freq>=a)&(freq<b)].mean()) if np.any((freq>=a)&(freq<b)) else 0 for a,b in zip(edges[:-1],edges[1:])])
            levels=np.log1p(bands); levels=levels/max(.3,float(levels.max()))*self.energy
            self.band_levels=self.band_levels*.65+levels*.35
            flux=max(0.,rms-self.previous_rms); self.previous_rms=rms
            self.flux_mean+=(flux-self.flux_mean)*(1-math.exp(-dt/.7))
            self.envelope.append((self.elapsed,rms if active else 0.))
            if active and flux>max(threshold*.8,self.flux_mean*2.2) and self.elapsed-self.last_beat>.26:
                self.last_beat=self.elapsed; self.onsets.append(self.elapsed); self.beats+=1
            if self.elapsed-self.last_tempo>.5:
                self.last_tempo=self.elapsed; self._tempo()

    def _tempo(self):
        if len(self.envelope)<80 or self.envelope[-1][0]-self.envelope[0][0]<3:return
        times,values=np.asarray(self.envelope,dtype=float).T
        grid=np.arange(max(times[0],times[-1]-12),times[-1],.02)
        values=np.interp(grid,times,values); values-=values.mean()
        power=float(values@values)
        if power<1e-7:self.bpm=0.; self.confidence=0.; return
        corr=np.correlate(values,values,"full")[len(values)-1:]/power
        lags=np.arange(round(60/190/.02),round(60/65/.02)+1)
        scores=corr[lags]
        if self.bpm:scores=scores+.035*np.exp(-((60/(lags*.02)-self.bpm)/12)**2)
        lag=int(lags[int(np.argmax(scores))]); confidence=max(0.,float(corr[lag]))
        self.confidence=confidence
        if confidence>.15:
            estimate=60/(lag*.02)
            self.bpm=estimate if not self.bpm or abs(estimate-self.bpm)>15 else self.bpm*.7+estimate*.3

    def snapshot(self):
        with self.lock:
            age=max(0.,time.monotonic()-self.last_sample) if self.last_sample else 20
            decay=math.exp(-max(0.,age-.15)*5)
            energy=self.energy*decay; bpm=self.bpm if energy>.025 else 0.
            beat=math.exp(-max(0,self.elapsed-self.last_beat+age)*7)*decay
            if energy<.035:style,mood="等待音乐","安静"
            elif bpm>=145:style,mood="高速电子 / 鼓打贝斯","激昂"
            elif bpm>=115 and self.bass>.14:style,mood="舞曲 / 电子","热烈" if energy>.6 else "律动"
            elif bpm and bpm<95 and self.centroid<2200:style,mood="氛围 / 慢拍","沉静"
            elif self.centroid>3000:style,mood="明亮 / 流行","明亮"
            else:style,mood="律动 / 综合","律动"
            return {"bpm":round(bpm,1),"confidence":round(self.confidence,2),"energy":energy,"bass":self.bass*decay,
                    "mid":self.mid*decay,"treble":self.treble*decay,"centroid":self.centroid,"beat":beat,"beats":self.beats,
                    "bands":self.band_levels.tolist() if decay>.5 else (self.band_levels*decay).tolist(),"style":style,"mood":mood}


def led_frame(rgb,brightness=1.):
    pixels=np.asarray(rgb,dtype=np.uint8); height,width,_=pixels.shape
    pixels=np.clip(pixels.astype(float)*brightness,0,255).astype(np.uint8)
    frame={(x,y+1):tuple(int(c) for c in pixels[y,x]) for y in range(height) for x in range(width)}
    frame.update({(x,0):tuple(int(c) for c in pixels[0,x]) for x in range(width)})
    frame.update({(width,y+1):tuple(int(c) for c in pixels[y,-1]) for y in range(height)})
    return frame


class VJController:
    """An isolated GPU/output process; the Tk event loop drains its bounded queue."""
    def __init__(self):
        self.process=None; self.commands=None; self.events=None; self.stop_event=None
        self.state={"running":False}; self.config={}

    def start(self,config):
        from .vj_output import run_vj
        self.stop()
        if self.process and self.process.is_alive():raise RuntimeError("VJ 输出仍在安全退出，请稍后重试")
        context=mp.get_context("spawn")
        self.commands=context.Queue(maxsize=8); self.events=context.Queue(maxsize=3); self.stop_event=context.Event()
        self.config=dict(config); self.state={"running":True,"starting":True}
        self.process=context.Process(target=run_vj,args=(self.config,self.commands,self.events,self.stop_event),name="VJOutput",daemon=True)
        self.process.start()

    def update(self,config):
        self.config=dict(config)
        if self.process and self.process.is_alive():
            try:self.commands.put_nowait(self.config)
            except queue.Full:
                try:self.commands.get_nowait()
                except queue.Empty:pass
                try:self.commands.put_nowait(self.config)
                except queue.Full:pass

    def poll(self):
        messages=[]
        if self.events:
            while True:
                try:messages.append(self.events.get_nowait())
                except queue.Empty:break
        for message in messages:
            if "state" in message:self.state=message["state"]
        if self.process and not self.process.is_alive():
            self.state["running"]=False
            if self.process.exitcode and not any("error" in m for m in messages):
                messages.append({"error":f"VJ 输出进程退出（{self.process.exitcode}），请查看 data/vj.log"})
            self.process.join(); self.process=None
        return messages

    def stop(self):
        if self.stop_event:self.stop_event.set()
        deadline=time.monotonic()+4
        while self.process and self.process.is_alive() and time.monotonic()<deadline:
            if self.events:
                try:
                    while True:self.events.get_nowait()
                except queue.Empty:pass
            self.process.join(timeout=.05)
        if self.process and self.process.is_alive():return
        for channel in (self.commands,self.events):
            if channel:channel.cancel_join_thread(); channel.close()
        self.process=None; self.commands=None; self.events=None; self.state={"running":False}
