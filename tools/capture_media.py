"""Capture real Launchpad Studio UI screenshots and a short README demo."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
import sys
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import ImageGrab

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from core.rhythm import RhythmGame, chart_from_analysis


OUTPUT=Path(__file__).resolve().parents[1]/"docs"/"media"


def capture(window):
    window.update_idletasks(); window.update(); time.sleep(.025)
    x,y=window.winfo_rootx(),window.winfo_rooty()
    screen=ImageGrab.grab(); sx=screen.width/window.winfo_screenwidth(); sy=screen.height/window.winfo_screenheight()
    box=(round(x*sx),round(y*sy),round((x+window.winfo_width())*sx),round((y+window.winfo_height())*sy))
    return screen.crop(box).resize((window.winfo_width(),window.winfo_height())).convert("RGB")


def performance_demo(window,phase):
    stats={"CPU":45+35*np.sin(phase),"RAM":62,"磁盘":38,"GPU":55+35*np.cos(phase*.8),
           "网络 MB/s":4.8,"磁盘 MB/s":12.5,"cores":[35,55,72,48,80,42,67,30],
           "temperatures":{"CPU":67.0,"GPU":61.0,"主板":43.0,"存储":48.0}}
    for key,label in window.metric_labels.items():
        value=stats[key]; label.configure(text=f"{value:.1f}%" if key in ("CPU","RAM","GPU","磁盘") else f"{value:.1f}")
    for key,label in window.temp_labels.items():label.configure(text=f"{stats['temperatures'][key]:.1f} °C",fg=app.GOOD)
    window.apply_frame(window.performance.frame(stats,"霓虹",.9))


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    app.LaunchpadStudio._start_tray=lambda self:None
    app.LaunchpadDevice.devices=staticmethod(lambda:([],[]))
    with tempfile.TemporaryDirectory() as temp:
        app.ROOT=Path(temp)
        window=app.LaunchpadStudio(); window.geometry("1280x820+30+30"); window.deiconify(); window.lift(); window.update()
        window._show_mode("性能监控"); performance_demo(window,.4)
        overview=capture(window); overview.save(OUTPUT/"overview.png",optimize=True)

        frames=[]
        for phase in np.linspace(0,5,18):
            performance_demo(window,float(phase)); frames.append(capture(window))

        sr=8000; t=np.arange(sr*7)/sr; samples=(np.sin(2*np.pi*220*t)*.04).astype(np.float32)
        for second in range(1,7):samples[second*sr:second*sr+350]+=.8*np.hanning(350).astype(np.float32)
        analysis=SimpleNamespace(data=samples,sr=sr,duration=7.0,bpm=120)
        chart=chart_from_analysis(analysis,"demo-song.wav","环形音游","普通",8)
        game=RhythmGame(); game.reset(chart,3,"普通")
        window._show_mode("工具与游戏"); window.utility_choice.set("环形音游"); window._build_utility_options()
        window.rhythm_file_label.configure(text="demo-song.wav")
        window.utility_info.configure(text=f"谱面已生成 · BPM {chart.bpm} · {len(chart.notes)} 个音符 · 8 键\n得分 12600 · 连击 18")
        low,high=window._utility_colors()
        window.apply_frame(game.frame(2.25,low,high,.95)); rhythm=capture(window); rhythm.save(OUTPUT/"rhythm-game.png",optimize=True)
        for position in np.linspace(.4,6.2,42):
            game.update(float(position)); window.apply_frame(game.frame(float(position),low,high,.95)); frames.append(capture(window))

        width,height=frames[0].size
        writer=cv2.VideoWriter(str(OUTPUT/"launchpad-studio-demo.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),10,(width,height))
        for frame in frames:writer.write(cv2.cvtColor(np.asarray(frame),cv2.COLOR_RGB2BGR))
        writer.release()
        gif=[frame.resize((768,round(height*768/width))) for frame in frames[::2]]
        gif[0].save(OUTPUT/"launchpad-studio-demo.gif",save_all=True,append_images=gif[1:],duration=200,loop=0,optimize=True)
        window._close()
    print(f"Captured {len(frames)} frames in {OUTPUT}")


if __name__=="__main__":main()
