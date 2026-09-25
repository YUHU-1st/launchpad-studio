from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .audio_engine import AudioAnalysis
from .miniapps import blank
from .performance import mix


@dataclass(frozen=True)
class RhythmNote:
    time: float
    lane: int


@dataclass
class RhythmChart:
    path: str
    style: str
    difficulty: str
    lanes: int
    bpm: int
    duration: float
    notes: list[RhythmNote]


def generate_chart(path, style="瀑布音游", difficulty="普通", lanes=6):
    analysis=AudioAnalysis(path)
    return chart_from_analysis(analysis,str(path),style,difficulty,lanes),analysis


def chart_from_analysis(analysis, path="", style="瀑布音游", difficulty="普通", lanes=6):
    lanes=max(4,min(8,int(lanes))); data=np.asarray(analysis.data,dtype=np.float32)
    sr=max(1,int(analysis.sr)); duration=float(analysis.duration); hop=512
    if len(data)<hop:
        return RhythmChart(path,style,difficulty,lanes,int(analysis.bpm),duration,[])
    chunks=data[:len(data)//hop*hop].reshape(-1,hop)
    rms=np.sqrt(np.mean(chunks*chunks,axis=1)+1e-10)
    onset=np.maximum(0,np.diff(rms,prepend=rms[0]))
    local=(onset>=np.roll(onset,1))&(onset>np.roll(onset,-1))
    percentile={"简单":82,"普通":70,"困难":57}.get(difficulty,70)
    threshold=float(np.percentile(onset,percentile)) if np.any(onset) else 0
    peak_times=np.flatnonzero(local&(onset>=max(threshold,1e-5)))*hop/sr

    beat=max(.28,min(1.0,60/max(60,int(analysis.bpm))))
    subdivision={"简单":1,"普通":2,"困难":3}.get(difficulty,2)
    anchor=float(peak_times[0]) if len(peak_times) else 1.0
    grid=np.arange(max(.8,anchor),max(.8,duration-.25),beat/subdivision)
    # Strong transients are always retained; beat-grid notes make quiet but
    # rhythmic passages playable.  Difficulty changes density and spacing.
    candidates=np.sort(np.r_[peak_times,grid])
    min_gap={"简单":.28,"普通":.17,"困难":.105}.get(difficulty,.17)
    times=[]
    for value in candidates:
        value=float(value)
        if value<.65 or value>duration-.15:continue
        if not times or value-times[-1]>=min_gap:times.append(value)

    notes=[]; previous=-1
    edges=np.geomspace(55,min(12000,sr/2),lanes+1)
    for index,value in enumerate(times):
        center=round(value*sr); sample=data[max(0,center-1024):min(len(data),center+1024)]
        if len(sample)>=64:
            spectrum=np.abs(np.fft.rfft(sample*np.hanning(len(sample))))
            freqs=np.fft.rfftfreq(len(sample),1/sr)
            energy=[float(spectrum[(freqs>=lo)&(freqs<hi)].sum()) for lo,hi in zip(edges[:-1],edges[1:])]
            lane=int(np.argmax(energy))
        else:lane=index%lanes
        if lane==previous:lane=(lane+1+index%max(1,lanes-1))%lanes
        previous=lane; notes.append(RhythmNote(value,lane))
    return RhythmChart(path,style,difficulty,lanes,int(analysis.bpm),duration,notes)


class RhythmGame:
    def __init__(self):
        self.chart=None; self.reset(None)

    def reset(self,chart,fall_speed=3,difficulty="普通"):
        self.chart=chart; self.fall_speed=max(1,min(5,int(fall_speed))); self.difficulty=difficulty
        self.states=[0]*len(chart.notes) if chart else []
        self.score=0; self.combo=0; self.max_combo=0; self.hits=0; self.misses=0; self.running=bool(chart)

    @property
    def hit_window(self):return {"简单":.24,"普通":.17,"困难":.12}.get(self.difficulty,.17)

    @property
    def lead_time(self):return {1:3.6,2:3.0,3:2.35,4:1.8,5:1.35}[self.fall_speed]

    def targets(self, output_size=(8, 8)):
        if not self.chart:return []
        width,height=(max(1,int(value)) for value in output_size)
        if self.chart.style=="瀑布音游":
            return [(round(i*(width-1)/(self.chart.lanes-1)),height) for i in range(self.chart.lanes)]
        center_x,center_y=(width-1)/2,(height+1)/2
        radius_x,radius_y=max(0,(width-1)/2),max(0,(height-1)/2)
        return [(round(center_x+radius_x*math.cos(-math.pi/2+i*2*math.pi/self.chart.lanes)),
                 round(center_y+radius_y*math.sin(-math.pi/2+i*2*math.pi/self.chart.lanes)))
                for i in range(self.chart.lanes)]

    def update(self,position):
        if not self.chart:return
        for i,note in enumerate(self.chart.notes):
            if self.states[i]==0 and note.time<position-self.hit_window:
                self.states[i]=-1; self.misses+=1; self.combo=0
        if position>=self.chart.duration or (self.states and all(self.states) and position>self.chart.notes[-1].time+.5):
            self.running=False

    def hit(self,xy,position,output_size=(8, 8)):
        if not self.running or not self.chart:return None
        try:lane=self.targets(output_size).index(xy)
        except ValueError:
            self.misses+=1; self.combo=0; return "miss"
        choices=[(abs(note.time-position),i) for i,note in enumerate(self.chart.notes)
                 if self.states[i]==0 and note.lane==lane and abs(note.time-position)<=self.hit_window]
        if not choices:
            self.misses+=1; self.combo=0; return "miss"
        error,index=min(choices); self.states[index]=1; self.hits+=1; self.combo+=1; self.max_combo=max(self.max_combo,self.combo)
        grade="perfect" if error<=.055 else "great" if error<=.11 else "good"
        self.score+=({"perfect":1000,"great":700,"good":400}[grade])*(1+min(20,self.combo)//10)
        return grade

    def frame(self,position,low=(60,80,180),high=(80,240,255),brightness=1.0,output_size=(8, 8)):
        width,height=(max(1,int(value)) for value in output_size)
        frame=blank((width,height))
        if not self.chart:return frame
        targets=self.targets((width,height)); dim=tuple(round(c*.22*brightness) for c in high)
        for target in targets:frame[target]=dim
        for state,note in zip(self.states,self.chart.notes):
            if state!=0:continue
            remaining=note.time-position
            if not (-self.hit_window<=remaining<=self.lead_time):continue
            progress=max(0,min(1,1-remaining/self.lead_time)); color=tuple(round(c*brightness) for c in mix(low,high,progress))
            tx,ty=targets[note.lane]
            if self.chart.style=="瀑布音游":xy=(tx,max(1,min(height,1+round(progress*(height-1)))))
            else:
                center_x,center_y=(width-1)/2,(height+1)/2
                xy=(round(center_x+(tx-center_x)*progress),round(center_y+(ty-center_y)*progress))
                xy=(max(0,min(width-1,xy[0])),max(1,min(height,xy[1])))
            old=frame.get(xy,(0,0,0)); frame[xy]=tuple(max(a,b) for a,b in zip(old,color))
        progress=0 if not self.chart.duration else max(0,min(1,position/self.chart.duration))
        for x in range(round(progress*width)):frame[(x,0)]=tuple(round(c*brightness) for c in high)
        for i in range(min(height,self.combo)):frame[(width,height-i)]=tuple(round(c*brightness) for c in low)
        if not self.running:
            pulse=tuple(round(c*brightness) for c in high)
            middle=max(1,height//2)
            for x in range(width):frame[(x,middle)]=pulse; frame[(x,min(height,middle+1))]=pulse
        return frame
