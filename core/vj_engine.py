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
VJ_LED_STYLES = ("自动联动", "像素频谱", "镜像频谱", "节拍方环", "弹跳光柱", "像素雨幕", "扫描激光", "旋转射线", "棋盘冲击", "像素螺旋", "节拍箭头", "粒子爆发", "音浪线条", "原画采样")


def display_targets():
    from screeninfo import get_monitors
    return [{"id":m.name or str(i), "label":f"显示器 {i+1} · {m.width}×{m.height}"+(" · 主屏" if m.is_primary else ""),
             "x":m.x, "y":m.y, "width":m.width, "height":m.height} for i,m in enumerate(get_monitors())]


def validate_vj_config(raw):
    """Validate desktop/mobile settings at the user-input boundary."""
    cfg=dict(raw)
    if cfg["style"] not in VJ_STYLES or cfg["aspect"] not in VJ_ASPECTS or cfg["led_style"] not in VJ_LED_STYLES:
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
    for key,lo,hi in (("sensitivity",.1,4),("threshold",0,.2),("speed",.1,3),("intensity",.1,2),("detail",.3,2),("scene_seconds",4,120),
                      ("led_speed",.1,3),("led_intensity",.1,2),("led_density",.3,2),("led_contrast",1,5),("led_threshold",0,.9)):
        value=float(cfg[key])
        if not math.isfinite(value) or not lo<=value<=hi:raise ValueError(f"{key} 超出可调范围")
        cfg[key]=value
    if not isinstance(cfg["screens"],list) or any(not isinstance(item,str) for item in cfg["screens"]):raise ValueError("投屏目标无效")
    if len(cfg["screens"])!=len(set(cfg["screens"])):raise ValueError("投屏目标不能重复")
    if not isinstance(cfg["launchpads"],list) or any(not isinstance(item,str) for item in cfg["launchpads"]) or len(set(cfg["launchpads"]))!=len(cfg["launchpads"]):
        raise ValueError("灯板目标必须为不重复的设备 ID")
    for key in ("preview","alpha","map_launchpad"):
        if not isinstance(cfg[key],bool):raise ValueError("VJ 开关参数必须为布尔值")
    if cfg["map_launchpad"] and not cfg["launchpads"]:raise ValueError("请至少选择一块 Launchpad")
    if not cfg["preview"] and not cfg["screens"]:
        if not cfg["map_launchpad"]:raise ValueError("请至少选择一种输出：预览、显示器或 Launchpad")
        if cfg["led_style"]=="原画采样":raise ValueError("原画采样需要开启预览或投屏；仅灯板输出请选择原生灯效")
    return cfg


def vj_colors(cfg,features):
    from .performance import PALETTES
    palette=cfg["palette"]
    if palette=="自动配色":palette="海洋" if features["mood"]=="沉静" else "日落" if features["mood"] in ("激昂","热烈") else "霓虹"
    if palette=="自定义":
        h=cfg["custom_color"].lstrip("#"); high=tuple(int(h[i:i+2],16) for i in (0,2,4)); return tuple(v*.18 for v in high),high
    return PALETTES[palette]


def vj_led_layout(configs,selected,link_mode):
    from .multi_launchpad import canvas_geometry, LINK_MIRROR
    items=[item for item in configs if str(item["id"]) in selected]
    width,height,positions=canvas_geometry(items)
    return ((8,8) if link_mode==LINK_MIRROR else (width*8,height*8)),positions,items


def vj_led_routes(frame,configs,pads_by_id,selected,link_mode):
    from .multi_launchpad import device_frame, LINK_MIRROR
    size,positions,items=vj_led_layout(configs,selected,link_mode)
    return {str(item["id"]):device_frame(frame,pads_by_id[str(item["id"])],positions[str(item["id"])],
            (size[0]//8,size[1]//8),extend=link_mode!=LINK_MIRROR) for item in items if str(item["id"]) in pads_by_id}


def native_led_pixels(cfg,features,clock,scene):
    """Hard-edged native pad pixels, with the screen's palette and beat envelope."""
    width,height=cfg["output_size"]; y,x=np.mgrid[0:height,0:width]
    t=clock*cfg["led_speed"]; density=cfg["led_density"]
    px=x-(width-1)/2; py=y-(height-1)/2; radius=np.maximum(np.abs(px),np.abs(py))
    energy=features["energy"]; beat=features["beat"]; count=features["beats"]
    style=cfg["led_style"]
    if style=="自动联动":style=("节拍方环","扫描激光","粒子爆发","像素雨幕","像素螺旋","音浪线条","像素频谱","棋盘冲击")[scene]
    level=np.zeros((height,width),dtype=float)
    if style in ("像素频谱","镜像频谱"):
        bands=np.interp(np.linspace(0,31,width),np.arange(32),features["bands"])
        if style=="像素频谱":level=(height-1-y<np.ceil(bands[None,:]*height))*(.55+.45*bands[None,:])
        else:level=(np.abs(py)<np.ceil(bands[None,:]*height/2))*(.55+.45*bands[None,:])
    elif style=="节拍方环":
        ring=(t*(1+energy)+count*.5)%max(2,min(width,height)/2)
        level=(np.abs(radius-ring)<.7)*(.7+.3*beat)
    elif style=="弹跳光柱":
        columns=np.sin(np.arange(width)*density+t*3.)*.5+.5
        level=(height-1-y<np.ceil(columns[None,:]*height*(.3+.7*energy)))*(.55+.45*beat)
    elif style=="像素雨幕":
        heads=(t*(3+energy*6)+np.sin(np.arange(width)*12.9898)*height)%height
        distance=(y-heads[None,:])%height
        level=np.maximum(0,1-distance/(1+2*density))*(.7+.3*beat)
    elif style=="扫描激光":
        level=np.maximum((x==int(t*(3+energy*4))%width), (y==int(t*2+count)%height))*(.7+.3*beat)
    elif style=="旋转射线":
        angle=t*.8+count*.3; distance=np.abs(px*np.sin(angle)-py*np.cos(angle))
        level=(distance<.65*density)*(.65+.35*beat)
    elif style=="棋盘冲击":
        size=max(1,round(2/density)); level=((x//size+y//size+count)%2==0)*(.5+.5*beat)
    elif style=="像素螺旋":
        phase=np.arctan2(py,px)+radius*.7*density-t*2
        level=(np.cos(phase*2)>.45)*(.6+.4*beat)
    elif style=="节拍箭头":
        shift=(t*3+count)%(width+height)
        level=(np.mod(x-np.abs(py)-shift,width)<max(1,round(density)))*(.7+.3*beat)
    elif style=="粒子爆发":
        distance=np.sqrt(px*px+py*py); ring=(t*(2+energy*4)+count*.4)%max(1,float(distance.max()))
        particles=np.sin(x*12.98+y*78.23+count*4.1)
        level=(np.abs(distance-ring)<1.1*density)*(particles>-.25)*(.65+.35*beat)
    elif style=="音浪线条":
        wave=(height-1)/2+np.sin(np.arange(width)*.6*density-t*3)*(height-1)*(.15+.3*energy)
        level=(np.abs(y-wave[None,:])<.7)*(.6+.4*beat)
    level=np.clip((level-cfg["led_threshold"])*cfg["led_contrast"],0,1)
    level*=min(1,cfg["led_intensity"]*(.55+.45*energy))
    low,high=vj_colors(cfg,features); high=np.asarray(high,dtype=float); low=np.asarray(low,dtype=float)
    # Saturated palette colours on true black; no bloom, antialiasing or dim haze.
    hue=.25+.75*(np.sin((x+y)*.24+t*.3)*.5+.5)
    colors=low[None,None,:]*(1-hue[:,:,None])+high[None,None,:]*hue[:,:,None]
    colors*=255/np.maximum(1,colors.max(axis=2,keepdims=True))
    return np.clip(colors*level[:,:,None],0,255).astype(np.uint8),style


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
