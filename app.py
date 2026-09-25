from __future__ import annotations

import os
import json
from pathlib import Path
import ctypes
import faulthandler
import logging
import queue
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog, ttk
from PIL import Image, ImageDraw
import pystray

from core.launchpad import ALL_PADS, MODELS, LaunchpadDevice, is_launchpad_control_port
from core.multi_launchpad import (LINK_EXTEND, LINK_INDEPENDENT, LINK_MIRROR, LINK_MODES,
                                  MODE_SOURCES, canvas_geometry, normalize_configs, number_frame, route_frames)
from core.settings import AUDIO_DETAIL_DEFAULTS, VIDEO_DETAIL_DEFAULTS, Settings
from core.macros import MacroExecutor
from core.performance import PALETTES, PerformanceMonitor
from core.video_engine import VideoPlayer
from core.audio_engine import LiveAudio, MusicShow, audio_devices
from core.miniapps import SnakeGame, WhackAMole, blank, calendar_frame, clock_frame, scrolling_text, weather_frame
from core.rhythm import RhythmGame, generate_chart
from core.weather import WeatherService
from core.remote import RemoteServer
from core.windows_media import SystemMediaBridge


FROZEN = bool(getattr(sys,"frozen",False))
BUNDLE_ROOT = Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
APP_VERSION = (BUNDLE_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (BUNDLE_ROOT / "VERSION").exists() else "2.1.0"
PRODUCT_TITLE = "Launchpad Studio 2 · Matrix"
LOG_DIR = ROOT / "data"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=LOG_DIR / "crash.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(threadName)s %(message)s", encoding="utf-8")
_fault_log = open(LOG_DIR / "native_crash.log", "a", encoding="utf-8", buffering=1)
faulthandler.enable(_fault_log, all_threads=True)
def _uncaught(exc_type, exc_value, exc_tb):
    logging.critical("Uncaught application error", exc_info=(exc_type, exc_value, exc_tb))
sys.excepthook = _uncaught
_instance_mutex = None


def _single_instance():
    """Prevent duplicate tray services and bring the existing window forward."""
    global _instance_mutex
    if "--admin-restart" in sys.argv:
        return True
    create=ctypes.windll.kernel32.CreateMutexW
    create.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]; create.restype=ctypes.c_void_p
    _instance_mutex=create(None,False,"Local\\LaunchpadStudioMK2.Singleton")
    if ctypes.windll.kernel32.GetLastError()==183:
        find=ctypes.windll.user32.FindWindowW
        find.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p]; find.restype=ctypes.c_void_p
        hwnd=find(None,PRODUCT_TITLE) or find(None,"Launchpad Studio") or find(None,"Launchpad Studio MK2")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd,9); ctypes.windll.user32.SetForegroundWindow(hwnd)
        return False
    return True
BG, PANEL, PANEL2 = "#0b0d12", "#121620", "#191e2a"
TEXT, MUTED, ACCENT, GOOD, BAD = "#f3f5fb", "#8992a7", "#7c5cff", "#34d399", "#fb7185"


class PadCanvas(tk.Canvas):
    def __init__(self, master, on_click, on_layout_move, launchpad):
        super().__init__(master, bg=PANEL, highlightthickness=0, height=590, width=590)
        self.on_click = on_click
        self.on_layout_move = on_layout_move
        self.launchpad = launchpad
        self.items, self.colors, self.selected = {}, {}, None
        self.selected_device = None
        self.full_layout = False
        self.layout_configs = []
        self.layout_devices = {}
        self.device_frames = {}
        self._layout_signature = None
        self._hit_regions = []
        self._tile_regions = []
        self._drag = None
        self._layout_step = 1
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)

    def _geometry(self):
        w, h = max(300, self.winfo_width()), max(300, self.winfo_height())
        pads = self.launchpad.pads
        min_x, max_x = min(x for x,_ in pads), max(x for x,_ in pads)
        min_y, max_y = min(y for _,y in pads), max(y for _,y in pads)
        cols, rows = max_x-min_x+1, max_y-min_y+1
        cell = min((w-44)/cols, (h-44)/rows)
        ox, oy = (w-cols*cell)/2-min_x*cell, (h-rows*cell)/2-min_y*cell
        return ox, oy, cell

    def _single_device_id(self):
        return next((key for key,value in self.layout_devices.items() if value is self.launchpad),None)

    def draw(self):
        if self.full_layout and len(self.layout_configs)>1:
            return self._draw_full()
        return self._draw_single()

    def _draw_single(self):
        self.delete("all"); self.items.clear()
        self._hit_regions=[]; self._tile_regions=[]
        ox, oy, cell = self._geometry()
        self.create_text(max(10,ox), 12, text=f"{self.launchpad.model.name.upper()} · {len(self.launchpad.pads)} LED CANVAS", anchor="nw",
                         fill=MUTED, font=("Segoe UI", 9, "bold"))
        for x, y in self.launchpad.pads:
            gap = cell * .15
            x1, y1 = ox+x*cell+gap, oy+y*cell+gap
            x2, y2 = ox+(x+1)*cell-gap, oy+(y+1)*cell-gap
            rgb = self.colors.get((x,y), (17,21,30))
            fill = "#%02x%02x%02x" % rgb
            outline = "#ffffff" if self.selected == (x,y) else "#31394b"
            width = 3 if self.selected == (x,y) else 1
            if y in (0,9) or x in (-1,8):
                item = self.create_oval(x1+cell*.1, y1+cell*.1, x2-cell*.1, y2-cell*.1,
                                        fill=fill, outline=outline, width=width)
            else:
                item = self.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline,
                                             width=width)
            self.items[(x,y)] = item
            self._hit_regions.append((self._single_device_id(),x,y,x1,y1,x2,y2))
            if cell > 48:
                self.create_text((x1+x2)/2, (y1+y2)/2, text=self.launchpad.pad_label(x,y),
                                 fill="#ffffff" if sum(rgb)>250 else "#657087",
                                 font=("Segoe UI", 7))

    def _draw_full(self):
        self.delete("all"); self.items.clear(); self._hit_regions=[]; self._tile_regions=[]
        width,height,positions=canvas_geometry(self.layout_configs)
        canvas_w,canvas_h=max(300,self.winfo_width()),max(300,self.winfo_height())
        margin,header=18,42
        tile_size=max(42,min((canvas_w-margin*2)/max(1,width),(canvas_h-header-margin)/max(1,height)))
        total_w,total_h=width*tile_size,height*tile_size
        base_x=(canvas_w-total_w)/2; base_y=header+(canvas_h-header-total_h)/2
        self._layout_step=tile_size
        self.create_text(margin,10,text=f"完整拼接画布 · {len(self.layout_configs)} DEVICES · {width*8}×{height*8} CORE · 拖动板块调整布局",
                         anchor="nw",fill=MUTED,font=("Segoe UI",9,"bold"))
        for config in self.layout_configs:
            device_id=str(config.get("id")); device=self.layout_devices.get(device_id)
            model=device.model if device else self.launchpad.model
            tile_x,tile_y=positions[device_id]
            left=base_x+tile_x*tile_size; top=base_y+tile_y*tile_size
            cell=max(3,min((tile_size-18)/10,(tile_size-28)/10))
            board_w=board_h=cell*10
            ox=left+(tile_size-board_w)/2; oy=top+24+(tile_size-24-board_h)/2
            selected_tile=self.selected_device==device_id
            tag=f"tile-{device_id}"
            self.create_rectangle(ox-5,oy-22,ox+board_w+5,oy+board_h+5,fill="#10141d",
                                  outline=ACCENT if selected_tile else "#30384b",width=2,tags=(tag,"device-tile"))
            self.create_text(ox,oy-11,text=f"LP {config.get('number',1)} · ({config.get('x',0)},{config.get('y',0)}) · {config.get('mode','')}",
                             anchor="w",fill=TEXT if selected_tile else MUTED,font=("Segoe UI Semibold",8),tags=(tag,"device-tile"))
            self._tile_regions.append((device_id,ox-5,oy-22,ox+board_w+5,oy+board_h+5))
            frame=self.device_frames.get(device_id,{})
            for x,y in model.pads:
                gap=max(1,cell*.14); px=ox+(x+1)*cell; py=oy+y*cell
                x1,y1=px+gap,py+gap; x2,y2=px+cell-gap,py+cell-gap
                rgb=frame.get((x,y),(17,21,30)); fill="#%02x%02x%02x" % rgb
                selected=self.selected_device==device_id and self.selected==(x,y)
                outline="#ffffff" if selected else "#31394b"; line_width=3 if selected else 1
                if y in (0,9) or x in (-1,8):
                    item=self.create_oval(x1+cell*.08,y1+cell*.08,x2-cell*.08,y2-cell*.08,
                                          fill=fill,outline=outline,width=line_width,tags=(tag,"device-tile"))
                else:
                    item=self.create_rectangle(x1,y1,x2,y2,fill=fill,outline=outline,width=line_width,tags=(tag,"device-tile"))
                self.items[(device_id,x,y)]=item
                self._hit_regions.append((device_id,x,y,x1,y1,x2,y2))
                if cell>28:
                    self.create_text((x1+x2)/2,(y1+y2)/2,text=device.pad_label(x,y) if device else "",
                                     fill="#ffffff" if sum(rgb)>250 else "#657087",font=("Segoe UI",6),tags=(tag,"device-tile"))

    def _press(self,event):
        pad=next(((device_id,x,y) for device_id,x,y,x1,y1,x2,y2 in reversed(self._hit_regions)
                  if x1<=event.x<=x2 and y1<=event.y<=y2),None)
        tile=next((device_id for device_id,x1,y1,x2,y2 in reversed(self._tile_regions)
                   if x1<=event.x<=x2 and y1<=event.y<=y2),None)
        device_id=tile or (pad[0] if pad else None)
        if device_id is None:return
        self.selected_device=device_id
        if pad:self.selected=(pad[1],pad[2])
        config=next((item for item in self.layout_configs if str(item.get("id"))==device_id),{})
        self._drag={"device_id":device_id,"pad":pad,"start_x":event.x,"start_y":event.y,"last_x":0,"last_y":0,
                    "x":int(config.get("x",0)),"y":int(config.get("y",0)),"moved":False}

    def _motion(self,event):
        drag=self._drag
        if not drag or not self.full_layout:return
        if abs(event.x-drag["start_x"])+abs(event.y-drag["start_y"])<6:return
        drag["moved"]=True; step=max(1,self._layout_step)
        dx=round((event.x-drag["start_x"])/step)*step; dy=round((event.y-drag["start_y"])/step)*step
        self.move(f"tile-{drag['device_id']}",dx-drag["last_x"],dy-drag["last_y"]); drag["last_x"],drag["last_y"]=dx,dy

    def _release(self,event):
        drag=self._drag; self._drag=None
        if not drag:return
        if drag["moved"] and self.full_layout:
            step=max(1,self._layout_step)
            x=max(-8,min(8,drag["x"]+round((event.x-drag["start_x"])/step)))
            y=max(-8,min(8,drag["y"]+round((event.y-drag["start_y"])/step)))
            self.on_layout_move(drag["device_id"],x,y); return
        self.draw()
        if drag["pad"]:self.on_click(drag["pad"][1],drag["pad"][2],drag["device_id"])

    def select_pad(self,x,y,device_id=None):
        self.selected=(x,y); self.selected_device=device_id or self._single_device_id(); self.draw()

    def set_layout(self,configs,devices,full=False):
        configs=[dict(item) for item in configs]
        devices=dict(devices)
        full=bool(full and len(configs)>1)
        signature=(full,tuple((str(item.get("id")),int(item.get("number",1)),int(item.get("x",0)),int(item.get("y",0)),str(item.get("mode",""))) for item in configs),
                   tuple((key,value.model.key) for key,value in devices.items()))
        self.layout_configs,self.layout_devices,self.full_layout=configs,devices,full
        if signature!=self._layout_signature:
            self._layout_signature=signature; self.draw()

    def set_device_frames(self,frames):
        self.device_frames={str(key):dict(value) for key,value in frames.items()}
        if self.full_layout:self._refresh_colors()

    def _refresh_colors(self):
        if not self.items:return self.draw()
        for key,item in self.items.items():
            if len(key)==2:rgb=self.colors.get(key,(17,21,30))
            else:
                device_id,x,y=key; rgb=self.device_frames.get(device_id,{}).get((x,y),(17,21,30))
            self.itemconfigure(item,fill="#%02x%02x%02x" % rgb)

    def set_frame(self, frame):
        self.colors = frame
        if not self.full_layout:self._refresh_colors()


class LaunchpadStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.ui_events=queue.Queue(maxsize=24); self._closing=False
        self.title(PRODUCT_TITLE)
        self.geometry("1280x820")
        self.minsize(1060, 700)
        self.configure(bg=BG)
        try: self.iconbitmap(BUNDLE_ROOT / "app.ico")
        except Exception: pass
        self.settings_store = Settings(ROOT / "data" / "settings.json")
        remote_cfg=self.settings_store.data["remote"]
        if not remote_cfg.get("pin"):
            remote_cfg["pin"]=f"{secrets.randbelow(1_000_000):06d}"
            self.settings_store.save()
        initial_model=self.settings_store.data.get("launchpad_model","auto")
        self.lp = LaunchpadDevice(self._hardware_pad, initial_model if initial_model != "auto" else "mk2")
        self.launchpads={"lp1":self.lp}
        self.multi_cfg=self.settings_store.data["multi_launchpad"]
        self.layout_selected_id=None
        self.mode_frames={}
        self.active_modes=set()
        self._param_save_job=None; self._settings_save_job=None; self._parameter_clipboard=None
        self.macro_exec = MacroExecutor()
        self.performance = PerformanceMonitor()
        self.video = VideoPlayer(lambda frame:self.submit_frame(frame,"视频播放"), self.set_status, self._video_progress, self._video_finished)
        self.music = None
        self.live = None
        self.weather=WeatherService(); self.weather_data=None
        self.snake=SnakeGame(); self.mole=WhackAMole()
        self.rhythm_game=RhythmGame(); self.rhythm_chart=None; self.rhythm_analysis=None; self.rhythm_audio=None
        self.rhythm_chart_key=None; self.rhythm_generating=False
        self.utility_running=False; self.utility_job=None; self.utility_phase=0; self.active_utility=None
        self.score_effect_token=0; self.score_effect_until=0.0; self.rhythm_score_effect_until=0.0
        self.focus_deadline=None; self.focus_remaining=0; self.focus_paused=False
        self.mode = "性能监控"; self.active_mode=None
        self.running_perf = False
        self.last_perf_stats = {}
        self.video_path = ""
        self.audio_path = ""
        self.video_playlist = [p for p in self.settings_store.data.get("video_playlist",[]) if Path(p).exists()]
        self.audio_playlist = [p for p in self.settings_store.data.get("audio_playlist",[]) if Path(p).exists()]
        self.video_index = -1
        self.audio_index = -1
        self.video_duration = 0.0
        self.audio_duration = 0.0
        self.video_seeking = False
        self.audio_seeking = False
        self.selected_pad = (0,1)
        self.current_frame = {xy:(0,0,0) for xy in ALL_PADS}
        self.custom_color = self.settings_store.data.get("custom_color", "#7c5cff")
        h=self.custom_color.lstrip("#"); rgb=tuple(int(h[i:i+2],16) for i in (0,2,4))
        PALETTES["自定义"]=(tuple(int(v*.18) for v in rgb),rgb)
        self._build_style(); self._build_ui(); self._refresh_midi(); self._show_mode("性能监控")
        self.system_media=SystemMediaBridge(); self.system_media.start()
        self.remote_server=None; self.remote_tick_job=None
        if self.settings_store.data["remote"].get("enabled",True):self._restart_remote_server()
        self.bind("<KeyPress>",self._utility_key)
        self._start_tray()
        self.after(16,self._drain_ui_events)
        self.after(3000,self._midi_watchdog)
        self.after(250,self._remote_tick)
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

    def _build_style(self):
        s = ttk.Style(self); s.theme_use("clam")
        self.option_add("*TCombobox*Listbox.background",PANEL2)
        self.option_add("*TCombobox*Listbox.foreground",TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground",ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground","white")
        s.configure("TFrame", background=BG); s.configure("Panel.TFrame", background=PANEL)
        s.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        s.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        s.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        s.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 18))
        s.configure("Value.TLabel", background=PANEL2, foreground=TEXT, font=("Segoe UI Semibold", 18))
        s.configure("TButton", background=PANEL2, foreground=TEXT, borderwidth=0, padding=(12,8))
        s.map("TButton", background=[("active", "#252b3b")])
        s.configure("Accent.TButton", background=ACCENT, foreground="white", padding=(14,9))
        s.map("Accent.TButton", background=[("active", "#927aff")])
        s.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TEXT,
                    arrowcolor=TEXT, bordercolor="#30384b")
        s.map("TCombobox",fieldbackground=[("readonly",PANEL2)],foreground=[("readonly",TEXT)],
              selectbackground=[("readonly",PANEL2)],selectforeground=[("readonly",TEXT)])
        s.configure("TEntry", fieldbackground=PANEL2, foreground=TEXT, insertcolor=TEXT,
                    bordercolor="#30384b")
        s.configure("TScale", background=PANEL, troughcolor="#292f40")
        s.configure("TCheckbutton",background=BG,foreground=TEXT)

    def _build_ui(self):
        top = tk.Frame(self, bg=BG, height=72); top.pack(fill="x", padx=24, pady=(16,8)); top.pack_propagate(False)
        ttk.Label(top, text=PRODUCT_TITLE, style="Title.TLabel").pack(side="left", pady=14)
        self.status_dot = tk.Label(top, text="●", bg=BG, fg=BAD, font=("Segoe UI", 13)); self.status_dot.pack(side="left", padx=(18,5))
        self.device_status = tk.Label(top, text="未连接", bg=BG, fg=MUTED, font=("Segoe UI", 9)); self.device_status.pack(side="left")
        ttk.Button(top, text="布局设置", command=lambda:self._show_mode("布局设置")).pack(side="right", pady=12)
        ttk.Button(top, text="手机遥控", command=self._remote_dialog).pack(side="right", padx=8, pady=12)
        ttk.Button(top, text="灯光测试", command=self._test_lights).pack(side="right", padx=8, pady=12)
        ttk.Button(top,text="■ 全部停止并熄灯",command=self._stop_all_and_clear).pack(side="right",pady=12)

        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=24, pady=(0,18))
        side = tk.Frame(body, bg=PANEL, width=188); side.pack(side="left", fill="y"); side.pack_propagate(False)
        tk.Label(side, text="模式", bg=PANEL, fg=MUTED, font=("Segoe UI",9,"bold")).pack(anchor="w", padx=18, pady=(22,10))
        self.mode_buttons = {}
        icons = {"性能监控":"▥", "宏按键":"⌘", "视频播放":"▶", "音乐演示":"♫", "实时拾音":"≋", "工具与游戏":"◈", "布局设置":"▦"}
        for name in icons:
            b = tk.Button(side, text=f" {icons[name]}   {name}", anchor="w", bg=PANEL, fg=TEXT,
                          activebackground=PANEL2, activeforeground=TEXT, relief="flat",
                          font=("Segoe UI",10), padx=16, pady=12, cursor="hand2",
                          command=lambda n=name:self._show_mode(n))
            b.pack(fill="x", padx=7, pady=2); self.mode_buttons[name]=b
        tk.Frame(side,bg="#2a3040",height=1).pack(fill="x",padx=16,pady=18)
        tk.Label(side,text="整体色彩风格",bg=PANEL,fg=MUTED,font=("Segoe UI",9)).pack(anchor="w",padx=18)
        self.palette_var=tk.StringVar(value=self.settings_store.data.get("theme","霓虹"))
        pal=ttk.Combobox(side,textvariable=self.palette_var,values=list(PALETTES)+["自定义"],state="readonly",width=16)
        pal.pack(padx=16,pady=(6,8)); pal.bind("<<ComboboxSelected>>",self._palette_changed)
        ttk.Button(side,text="选择自定义颜色",command=self._pick_global_color).pack(padx=16,fill="x")
        tk.Label(side,text="亮度",bg=PANEL,fg=MUTED,font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=(16,0))
        self.brightness=tk.DoubleVar(value=self.settings_store.data.get("brightness",85))
        ttk.Scale(side,from_=10,to=100,variable=self.brightness,orient="horizontal",command=lambda _v:self._brightness_changed()).pack(padx=16,fill="x")
        self.model_footer=tk.Label(side,text=f"{self.lp.model.name} · {len(self.lp.pads)} LEDs",bg=PANEL,fg="#515a70",font=("Segoe UI",8))
        self.model_footer.pack(side="bottom",pady=16)

        self.center = tk.Frame(body,bg=PANEL); self.center.pack(side="left",fill="both",expand=True,padx=(12,12))
        canvas_tools=tk.Frame(self.center,bg=PANEL); canvas_tools.pack(fill="x",padx=12,pady=(9,0))
        tk.Label(canvas_tools,text="实际灯光画布 · 多设备可直接拖动调整位置",bg=PANEL,fg=MUTED,font=("Segoe UI",9,"bold")).pack(side="left")
        self.pad_canvas=PadCanvas(self.center,self._canvas_pad,self._canvas_layout_move,self.lp); self.pad_canvas.pack(fill="both",expand=True,padx=8,pady=(2,8))
        self.right=tk.Frame(body,bg=BG,width=330); self.right.pack(side="right",fill="y"); self.right.pack_propagate(False)
        page_host=tk.Frame(self.right,bg=BG); page_host.pack(fill="both",expand=True)
        self.page_canvas=tk.Canvas(page_host,bg=BG,highlightthickness=0,width=312)
        page_scroll=ttk.Scrollbar(page_host,orient="vertical",command=self.page_canvas.yview)
        self.page_canvas.configure(yscrollcommand=page_scroll.set)
        page_scroll.pack(side="right",fill="y"); self.page_canvas.pack(side="left",fill="both",expand=True)
        self.page=tk.Frame(self.page_canvas,bg=BG)
        self.page_window=self.page_canvas.create_window((0,0),window=self.page,anchor="nw")
        self.page.bind("<Configure>",lambda _e:self.page_canvas.configure(scrollregion=self.page_canvas.bbox("all")))
        self.page_canvas.bind("<Configure>",lambda e:self.page_canvas.itemconfigure(self.page_window,width=e.width))
        self.page_canvas.bind("<MouseWheel>",lambda e:self.page_canvas.yview_scroll(int(-e.delta/120),"units"))
        self.status_var=tk.StringVar(value="就绪")
        tk.Label(self.right,textvariable=self.status_var,bg=BG,fg=MUTED,font=("Segoe UI",9),anchor="w").pack(fill="x",pady=(8,0))
        # Pack the fixed-width inspector before the expanding LED canvas so it
        # keeps its full width at the default 1280 x 820 window size.
        self.center.pack_forget(); self.right.pack_forget()
        self.right.pack(side="right",fill="y"); self.center.pack(side="left",fill="both",expand=True,padx=(12,12))

    def _clear_page(self):
        for w in self.page.winfo_children(): w.destroy()
        self.page_canvas.yview_moveto(0)

    def _page_title(self, title, subtitle):
        ttk.Label(self.page,text=title,style="Title.TLabel").pack(anchor="w",pady=(4,3))
        tk.Label(self.page,text=subtitle,bg=BG,fg=MUTED,font=("Segoe UI",9),wraplength=310,justify="left").pack(anchor="w",pady=(0,18))

    def _card(self):
        f=tk.Frame(self.page,bg=PANEL2,padx=14,pady=12); f.pack(fill="x",pady=6); return f

    def _restart_remote_server(self):
        if self.remote_server:
            self.remote_server.stop(); self.remote_server=None
        cfg=self.settings_store.data["remote"]
        if not cfg.get("enabled",True):return
        try:
            self.remote_server=RemoteServer(BUNDLE_ROOT / "remote",cfg["pin"],int(cfg.get("port",8765)),
                                            self._remote_command_from_server,self.system_media)
            self.remote_server.start()
            if self.remote_server.error:
                self.set_status(f"手机遥控服务启动失败：{self.remote_server.error}")
            else:self.set_status(f"手机遥控已开启 · 端口 {cfg.get('port',8765)}")
        except Exception as exc:
            logging.error("Remote server failed",exc_info=True); self.set_status(f"手机遥控服务启动失败：{exc}")

    def _remote_command_from_server(self,action,value):
        self._queue_ui(("remote_command",action,value))

    def _remote_tick(self):
        if self._closing:return
        try:
            if self.remote_server:self.remote_server.update_app_state(self._remote_state())
        except Exception:logging.debug("Remote state update failed",exc_info=True)
        self.remote_tick_job=self.after(250,self._remote_tick)

    def _remote_led_grid(self,device_id):
        device=self.launchpads.get(str(device_id))
        if not device:return [""]*100
        return ["%02x%02x%02x" % device.colors[(x,y)] if (x,y) in device.colors else ""
                for y in range(10) for x in range(-1,9)]

    def _remote_state(self):
        def detail(mode):
            values=dict(self.settings_store.data["detail_params"].get(mode,{}))
            if self.mode=={"video":"视频播放","music":"音乐演示","live":"实时拾音"}.get(mode):
                values.update(self._detail_snapshot(mode))
            return values
        macros=[]
        for x,y in self.lp.pads:
            macro=self._macro_get(x,y)
            macros.append({"x":x,"y":y,"key":self._macro_key(x,y),"label":self.lp.pad_label(x,y),
                           "action":macro.get("action","") if macro else "","value":macro.get("value","") if macro else "",
                           "color":macro.get("color","#202633") if macro else "#202633","configured":bool(macro)})
        music_analysis=getattr(self.music,"analysis",None) if self.music else None
        music_pos=0.0
        if self.music and music_analysis:
            with self.music.lock:music_pos=float(self.music.cursor/music_analysis.sr)
        return {
            "version":1,"app_version":APP_VERSION,"product_name":PRODUCT_TITLE,
            "mode":self.mode,"active_mode":self.active_mode,"active_modes":sorted(self.active_modes),"active_utility":self.active_utility,
            "status":self.status_var.get(),
            "launchpad":{"connected":any(device.connected for device in self.launchpads.values()),"model":self.lp.model.name,"model_key":self.lp.model.key,
                         "models":[{"key":"auto","name":"自动识别"}]+[{"key":m.key,"name":m.name} for m in MODELS],
                         "inputs":list(getattr(self,"midi_inputs",[])),"outputs":list(getattr(self,"midi_outputs",[])),
                         "count":sum(device.connected for device in self.launchpads.values()),
                         "multi_enabled":bool(self.multi_cfg.get("enabled",False)),
                         "link_mode":self.multi_cfg.get("link_mode",LINK_EXTEND),
                         "link_modes":list(LINK_MODES),"mode_sources":list(MODE_SOURCES),
                         "devices":[{"id":item.get("id"),"number":item.get("number"),"x":item.get("x",0),"y":item.get("y",0),
                                     "mode":item.get("mode","性能监控"),"model":item.get("model","auto"),
                                      "model_name":self.launchpads[str(item.get("id"))].model.name if self.launchpads.get(str(item.get("id"))) else "自动识别",
                                      "led_grid":self._remote_led_grid(item.get("id")),
                                     "input":item.get("input",""),"output":item.get("output",""),
                                     "input_index":item.get("input_index",-1),"output_index":item.get("output_index",-1),
                                     "connected":bool(self.launchpads.get(str(item.get("id"))) and self.launchpads[str(item.get("id"))].connected)}
                                    for item in self.multi_cfg.get("devices",[])]},
            "global":{"palette":self.palette_var.get(),"palettes":list(PALETTES),"brightness":round(self.brightness.get()),
                      "custom_color":self.custom_color,"macro_control":bool(self.settings_store.data.get("macro_control_enabled",False))},
            "performance":dict(self.last_perf_stats),
            "macros":macros,
            "video":{"playlist":[Path(p).name for p in self.video_playlist],"index":self.video_index,
                     "position":round(float(getattr(self.video,"position",0.0)),3),"duration":round(float(getattr(self.video,"duration",0.0)),3),
                     "paused":bool(getattr(self.video,"paused",False)),"running":bool(self.video.thread and self.video.thread.is_alive()),
                     "detail":detail("video")},
            "music":{"playlist":[Path(p).name for p in self.audio_playlist],"index":self.audio_index,
                     "position":round(music_pos,3),"duration":round(float(getattr(music_analysis,"duration",0.0) or 0.0),3),
                     "paused":bool(getattr(self.music,"paused",False)) if self.music else False,
                     "running":bool(self.music and self.music.worker and self.music.worker.is_alive()),"detail":detail("music"),
                     "analysis":({"bpm":music_analysis.bpm,"mood":music_analysis.mood,"genre":music_analysis.genre,
                                  "energy":round(float(music_analysis.energy),3)} if music_analysis else {})},
            "live":{"devices":[{"id":i,"name":n} for i,n in getattr(self,"live_devices",[])],"selected":self.settings_store.data.get("live_device",""),
                    "running":bool(self.live and self.live.worker and self.live.worker.is_alive()),"detail":detail("live")},
            "utilities":{"allowed":["数字时钟","日历","天气","专注计时器"],"selected":self.settings_store.data["utilities"].get("selected","数字时钟"),
                         "running":bool(self.utility_running and self.active_utility in ("数字时钟","日历","天气","专注计时器")),
                         "weather_city":self.settings_store.data["utilities"].get("weather_city","北京"),"weather":self.weather_data or {},
                         "focus_minutes":self.settings_store.data["utilities"].get("focus_minutes",25),"focus_remaining":self.focus_remaining,
                         "focus_paused":self.focus_paused},
            "presets":{"video":self._preset_names("video"),"music":self._preset_names("music"),"live":self._preset_names("live")},
        }

    def _remote_dialog(self):
        win=tk.Toplevel(self); win.title("手机遥控"); win.geometry("510x430"); win.configure(bg=BG); win.transient(self)
        cfg=self.settings_store.data["remote"]
        tk.Label(win,text="局域网手机遥控",bg=BG,fg=TEXT,font=("Segoe UI Semibold",16)).pack(anchor="w",padx=22,pady=(20,4))
        tk.Label(win,text="手机与电脑连接同一局域网后，在 Android 客户端填写下方地址和配对 PIN。",
                 bg=BG,fg=MUTED,wraplength=455,justify="left").pack(anchor="w",padx=22,pady=(0,16))
        enabled=tk.BooleanVar(value=bool(cfg.get("enabled",True)))
        def toggle():
            cfg["enabled"]=bool(enabled.get()); self.settings_store.save(); self._restart_remote_server()
        ttk.Checkbutton(win,text="启用局域网遥控服务",variable=enabled,command=toggle).pack(anchor="w",padx=22)
        address=(self.remote_server.urls()[0] if self.remote_server and self.remote_server.urls() else f"http://127.0.0.1:{cfg.get('port',8765)}/")
        box=tk.Frame(win,bg=PANEL2,padx=14,pady=12); box.pack(fill="x",padx=22,pady=12)
        tk.Label(box,text="电脑地址",bg=PANEL2,fg=MUTED).pack(anchor="w")
        tk.Label(box,text=address,bg=PANEL2,fg=TEXT,font=("Consolas",11)).pack(anchor="w",pady=(2,10))
        tk.Label(box,text="配对 PIN",bg=PANEL2,fg=MUTED).pack(anchor="w")
        tk.Label(box,text=cfg["pin"],bg=PANEL2,fg=TEXT,font=("Segoe UI Semibold",24)).pack(anchor="w")
        def copy_pairing():
            self.clipboard_clear(); self.clipboard_append(f"{address}\n{cfg['pin']}"); self.update_idletasks(); self.set_status("手机遥控地址和 PIN 已复制")
        ttk.Button(win,text="复制地址和 PIN",command=copy_pairing).pack(fill="x",padx=22,pady=(2,6))
        def regenerate():
            cfg["pin"]=f"{secrets.randbelow(1_000_000):06d}"; self.settings_store.save(); self._restart_remote_server(); win.destroy(); self._remote_dialog()
        ttk.Button(win,text="重新生成配对 PIN",command=regenerate).pack(fill="x",padx=22,pady=6)
        clients=self.remote_server.connected_clients if self.remote_server else 0
        state="运行中" if self.remote_server and not self.remote_server.error else "未运行"
        tk.Label(win,text=f"服务：{state} · 已连接手机：{clients} 台 · 端口：{cfg.get('port',8765)}",
                 bg=BG,fg=GOOD if state=="运行中" else BAD).pack(anchor="w",padx=22,pady=(10,0))

    def _remote_show(self,name):
        if self.mode!=name:self._show_mode(name)

    def _handle_remote_command(self,action,value):
        try:
            if action=="app.stop":self._stop_all()
            elif action=="app.blackout":self._stop_all_and_clear()
            elif action=="app.test_lights":self._test_lights() if any(device.connected for device in self.launchpads.values()) else self.set_status("Launchpad 尚未连接")
            elif action=="mode.show" and value in self.mode_buttons:self._show_mode(value)
            elif action=="global.palette" and value in PALETTES:
                self.palette_var.set(value); self._palette_changed()
            elif action=="global.brightness":
                self.brightness.set(max(10,min(100,float(value)))); self._brightness_changed()
            elif action=="global.custom_color" and isinstance(value,str) and len(value)==7 and value.startswith("#"):
                int(value[1:],16); self.custom_color=value; self.settings_store.data["custom_color"]=value
                h=value[1:]; rgb=tuple(int(h[i:i+2],16) for i in (0,2,4)); PALETTES["自定义"]=(tuple(int(v*.18) for v in rgb),rgb)
                self.palette_var.set("自定义"); self._palette_changed()
            elif action=="macro_control":
                enabled=bool(value); self.settings_store.data["macro_control_enabled"]=enabled; self.settings_store.save(); self.set_status("宏按键并行控制已开启" if enabled else "宏按键并行控制已关闭")
            elif action=="performance.start":self._remote_show("性能监控"); self._start_perf()
            elif action=="macro.start":self._remote_show("宏按键"); self._start_macros()
            elif action=="macro.trigger":self._remote_macro_trigger(value)
            elif action=="macro.save":self._remote_macro_save(value)
            elif action=="macro.clear":self._remote_macro_clear(value)
            elif action.startswith("video."):self._remote_video(action[6:],value)
            elif action.startswith("music."):self._remote_music(action[6:],value)
            elif action.startswith("live."):self._remote_live(action[5:],value)
            elif action.startswith("utility."):self._remote_utility(action[8:],value)
            elif action.startswith("preset."):self._remote_preset(action[7:],value)
            elif action=="device.refresh":self._refresh_midi(); self.set_status("MIDI 设备列表已刷新")
            elif action=="device.multi.apply":self._remote_multi_apply(value)
            elif action=="device.layout.update":self._remote_layout_update(value)
            elif action=="device.auto_connect":self._auto_connect_launchpads()
            elif action=="device.identify":self._remote_identify(value)
            elif action=="device.connect":self._remote_connect(value)
        except Exception as exc:
            logging.warning("Remote command failed: %s",action,exc_info=True); self.set_status(f"手机遥控命令失败：{exc}")

    def _remote_xy(self,value):
        if not isinstance(value,dict):raise ValueError("按键参数无效")
        xy=(int(value.get("x")),int(value.get("y")))
        if xy not in self.lp.pads:raise ValueError("按键不存在")
        return xy

    def _remote_macro_trigger(self,value):
        xy=self._remote_xy(value); macro=self._macro_get(*xy)
        if macro:self.macro_exec.execute(macro); self.set_status(f"手机执行宏 {self.lp.pad_label(*xy)}")

    def _remote_macro_save(self,value):
        xy=self._remote_xy(value); action=str(value.get("action","热键")); macro_value=str(value.get("value","")); color=str(value.get("color","#7c5cff"))
        if action not in ["热键","输入文字","打开文件/程序","打开网址","执行命令","PowerShell","媒体控制","按键序列","鼠标操作","系统操作","设置音量","组合动作"]:raise ValueError("不支持的宏类型")
        if not (len(color)==7 and color.startswith("#")):color="#7c5cff"
        macros=self.settings_store.data["macros"]
        macros[self._macro_key(*xy)]={"action":action,"value":macro_value,"color":color}
        for alias in self._macro_aliases(*xy):macros.pop(alias,None)
        self.settings_store.save()
        if "宏按键" in self.active_modes:self._render_macro_profile()

    def _remote_macro_clear(self,value):
        xy=self._remote_xy(value); macros=self.settings_store.data["macros"]
        macros.pop(self._macro_key(*xy),None)
        for alias in self._macro_aliases(*xy):macros.pop(alias,None)
        self.settings_store.save()
        if "宏按键" in self.active_modes:self._render_macro_profile()

    def _remote_video(self,command,value):
        self._remote_show("视频播放")
        if command=="select":
            self.video_index=max(0,min(len(self.video_playlist)-1,int(value))) if self.video_playlist else -1
            if self.video_index>=0:self.video_list.selection_clear(0,"end"); self.video_list.selection_set(self.video_index)
        elif command=="play":self._start_video()
        elif command in ("pause","resume"):
            running=bool(self.video.thread and self.video.thread.is_alive())
            if running and bool(self.video.paused)==(command=="resume"):self._video_pause()
        elif command=="previous":self._advance_video(-1)
        elif command=="next":self._advance_video(1)
        elif command=="seek":self.video.seek(float(value))
        elif command=="rate":self.video_rate.set(str(value)); self.video.set_rate(self._rate(self.video_rate.get())); self._save_detail_now("video")
        elif command=="loop":self.video_loop.set(str(value)); self._save_detail_now("video")
        elif command=="effect":self.video_effect.set(str(value)); self._update_video_effect()
        elif command=="param" and isinstance(value,dict):
            for key,item in value.items():
                if key=="fps":self.video_fps.set(max(5,min(30,int(item))))
                elif key in self.video_vars:self.video_vars[key].set(float(item))
            self._update_video_effect()

    def _remote_music(self,command,value):
        self._remote_show("音乐演示")
        if command=="select":
            self.audio_index=max(0,min(len(self.audio_playlist)-1,int(value))) if self.audio_playlist else -1
            if self.audio_index>=0:self.audio_list.selection_clear(0,"end"); self.audio_list.selection_set(self.audio_index)
        elif command=="play":self._start_music()
        elif command in ("pause","resume"):
            running=bool(self.music and self.music.worker and self.music.worker.is_alive())
            if running and bool(self.music.paused)==(command=="resume"):self._audio_pause()
        elif command=="previous":self._advance_audio(-1)
        elif command=="next":self._advance_audio(1)
        elif command=="seek" and self.music:self.music.seek(float(value))
        elif command=="rate":self.audio_rate.set(str(value)); self.music and self.music.set_rate(self._rate(self.audio_rate.get())); self._save_detail_now("music")
        elif command=="loop":self.audio_loop.set(str(value)); self._save_detail_now("music")
        elif command=="volume":self.audio_volume.set(max(0,min(100,float(value)))); self._music_volume_changed()
        elif command=="style" and value in self._visual_styles():self.music_style.set(value); self._update_music_visual()
        elif command=="param" and isinstance(value,dict):
            for key,item in value.items():
                if key in self.music_visual_vars:self.music_visual_vars[key].set(float(item))
            self._update_music_visual()

    def _remote_live(self,command,value):
        self._remote_show("实时拾音")
        if command=="device":
            target=str(value); index=next((i for i,(device_id,name) in enumerate(self.live_devices) if device_id==target or name==target),-1)
            if index>=0:self.live_combo.current(index); self._live_device_changed()
        elif command=="start":self._start_live()
        elif command=="style" and value in self._visual_styles():self.live_style.set(value); self._update_live_visual()
        elif command=="param" and isinstance(value,dict):
            for key,item in value.items():
                if key in self.live_visual_vars:self.live_visual_vars[key].set(float(item))
            self._update_live_visual()

    def _remote_utility(self,command,value):
        allowed=("数字时钟","日历","天气","专注计时器")
        self._remote_show("工具与游戏")
        if command=="select":
            if value not in allowed:raise ValueError("手机端不提供游戏控制")
            self.utility_choice.set(value); self._utility_selection_changed()
        elif command=="start":
            if self.utility_choice.get() not in allowed:raise ValueError("手机端不提供游戏控制")
            self._start_utility()
        elif command=="stop":self._stop_utility(True)
        elif command=="weather_city":
            self.settings_store.data["utilities"]["weather_city"]=str(value).strip() or "北京"; self.settings_store.save()
            if self.utility_choice.get()=="天气":self.weather_city.set(self.settings_store.data["utilities"]["weather_city"])
        elif command=="focus_minutes":
            minutes=max(1,min(180,int(value))); self.settings_store.data["utilities"]["focus_minutes"]=minutes; self.settings_store.save()
            if self.utility_choice.get()=="专注计时器":self.focus_minutes.set(minutes)
        elif command=="focus_pause":self._pause_focus()
        elif command=="focus_reset":self._reset_focus()

    def _remote_preset(self,command,value):
        if not isinstance(value,dict):raise ValueError("预设参数无效")
        mode=str(value.get("mode","")); name=str(value.get("name","")).strip()
        page={"video":"视频播放","music":"音乐演示","live":"实时拾音"}.get(mode)
        if not page or not name:raise ValueError("预设名称无效")
        self._remote_show(page)
        if command=="load":
            values=self.settings_store.data["presets"][self._preset_group(mode)].get(name)
            if not values:raise ValueError("找不到预设")
            self._apply_detail_snapshot(mode,values); self._touch_recent(mode,name); self.settings_store.save()
        elif command=="save":
            self.settings_store.data["presets"][self._preset_group(mode)][name]=self._detail_snapshot(mode); self._touch_recent(mode,name); self.settings_store.save()

    def _remote_connect(self,value):
        if not isinstance(value,dict):raise ValueError("设备参数无效")
        self._refresh_midi(); in_name=str(value.get("input","")); out_name=str(value.get("output","")); model=str(value.get("model","auto"))
        if in_name not in self.midi_inputs or out_name not in self.midi_outputs:raise ValueError("所选 MIDI 端口已不存在")
        if model!="auto" and model not in {m.key for m in MODELS}:raise ValueError("Launchpad 型号无效")
        self.lp.connect(self.midi_inputs.index(in_name),self.midi_outputs.index(out_name),model)
        self.settings_store.data["launchpad_model"]=model; self.settings_store.save(); self._connected_ui()

    def _remote_multi_apply(self,value):
        if not isinstance(value,dict):raise ValueError("多设备参数错误")
        link_mode=str(value.get("link_mode",LINK_EXTEND))
        if link_mode not in LINK_MODES:raise ValueError("不支持的联动方式")
        raw_devices=value.get("devices")
        self.midi_inputs,self.midi_outputs=self.lp.devices()
        configs=normalize_configs(raw_devices,self.midi_inputs,self.midi_outputs,{"auto",*(model.key for model in MODELS)},link_mode)
        enabled=bool(value.get("enabled",False) and len(configs)>1)
        self.multi_cfg.update(enabled=enabled,link_mode=link_mode,devices=configs)
        self.settings_store.data["launchpad_model"]=configs[0]["model"]; self.settings_store.save()
        complete=self._connect_launchpad_configs(configs if enabled else configs[:1],silent=True)
        self._global_visual_update(); self._redispatch_frames()
        self.set_status(f"手机端已应用 {len(configs) if enabled else 1} 台 Launchpad · {link_mode}" if complete else "多设备配置已保存，部分 MIDI 端口连接失败")

    def _remote_layout_update(self,value):
        if not isinstance(value,dict):raise ValueError("布局参数错误")
        link_mode=str(value.get("link_mode",self.multi_cfg.get("link_mode",LINK_EXTEND)))
        if link_mode not in LINK_MODES:raise ValueError("不支持的联动方式")
        updates=value.get("devices",[])
        if not isinstance(updates,list):raise ValueError("设备布局错误")
        draft=json.loads(json.dumps(self.multi_cfg.get("devices",[]),ensure_ascii=False))
        current={str(item.get("id")):item for item in draft}
        for update in updates:
            item=current.get(str(update.get("id"))) if isinstance(update,dict) else None
            if not item:raise ValueError("布局中包含未知设备")
            x,y=int(update.get("x",item.get("x",0))),int(update.get("y",item.get("y",0)))
            mode=str(update.get("mode",item.get("mode","性能监控")))
            if not -8<=x<=8 or not -8<=y<=8:raise ValueError("设备坐标超出范围")
            if mode not in MODE_SOURCES:raise ValueError("设备模式无效")
            item.update(x=x,y=y,mode=mode)
        positions=[(int(item.get("x",0)),int(item.get("y",0))) for item in current.values()]
        if len(positions)!=len(set(positions)):raise ValueError("设备位置不能重叠")
        self.multi_cfg.update(link_mode=link_mode,devices=draft); self.settings_store.save()
        self._global_visual_update(); self._redispatch_frames(); self._sync_canvas_preview()
        if self.mode=="布局设置":self._show_mode("布局设置")
        self.set_status(f"手机端已更新布局 · {link_mode}")

    def _remote_identify(self,value):
        device_id=str(value.get("id","")) if isinstance(value,dict) else str(value or "")
        item=next((row for row in self.multi_cfg.get("devices",[]) if str(row.get("id"))==device_id),None)
        device=self.launchpads.get(device_id)
        if not item or not device or not device.connected:raise ValueError("设备尚未连接")
        device.set_frame(number_frame(item.get("number",1)),force=True); self.after(1800,self._redispatch_frames)
        self.set_status(f"正在用灯光显示 LP {item.get('number',1)}")

    def _macro_control_switch(self,parent=None):
        parent=parent or self.page
        self.macro_control_var=tk.BooleanVar(value=self.settings_store.data.get("macro_control_enabled",False))
        ttk.Checkbutton(parent,text="允许 Launchpad 按键同时触发已配置宏（不改变当前灯光）",
                        variable=self.macro_control_var,command=self._macro_control_changed).pack(fill="x",pady=(0,10))

    def _macro_control_changed(self):
        enabled=bool(self.macro_control_var.get())
        self.settings_store.data["macro_control_enabled"]=enabled; self.settings_store.save()
        self.set_status("宏按键并行控制已开启" if enabled else "宏按键并行控制已关闭")

    def _show_mode(self, name):
        previous={"视频播放":"video","音乐演示":"music","实时拾音":"live"}.get(getattr(self,"mode",None))
        if previous and self._detail_snapshot(previous):
            if self._param_save_job:
                try:self.after_cancel(self._param_save_job)
                except Exception:pass
                self._param_save_job=None
            self._save_detail_now(previous)
        # Page navigation is only configuration/navigation.  The currently
        # active light show keeps ownership until another mode is started.
        self.mode=name; self._clear_page()
        for n,b in self.mode_buttons.items(): b.configure(bg=PANEL2 if n==name else PANEL,fg="#c8bfff" if n==name else TEXT)
        {"性能监控":self._page_performance,"宏按键":self._page_macros,"视频播放":self._page_video,
         "音乐演示":self._page_music,"实时拾音":self._page_live,"工具与游戏":self._page_utilities,
         "布局设置":self._page_layout}[name]()

    def _page_layout(self):
        self._page_title("布局设置","像排列显示器一样拖动左侧 Launchpad；连接、联动和独立模式分配都在这里完成。")
        devices=list(self.multi_cfg.get("devices",[]))
        connected=sum(device.connected for device in self.launchpads.values())
        summary=self._card()
        tk.Label(summary,text=f"布局中 {len(devices)} 台 · 已连接 {connected} 台",bg=PANEL2,fg=TEXT,font=("Segoe UI Semibold",13)).pack(anchor="w")
        tk.Label(summary,text="自动识别会匹配全部 Launchpad 的 MIDI 输入/输出，无需手工选择端口。",bg=PANEL2,fg=MUTED,font=("Segoe UI",8),wraplength=275,justify="left").pack(anchor="w",pady=(4,8))
        ttk.Button(summary,text="扫描并连接全部 Launchpad",style="Accent.TButton",command=self._auto_connect_launchpads).pack(fill="x")
        tk.Label(self.page,text="联动方式",bg=BG,fg=MUTED,font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(14,6))
        mode_box=tk.Frame(self.page,bg=BG); mode_box.pack(fill="x")
        descriptions={LINK_EXTEND:"拼成一块大画布",LINK_MIRROR:"所有设备显示相同画面",LINK_INDEPENDENT:"每台运行不同功能"}
        current=self.multi_cfg.get("link_mode",LINK_EXTEND)
        for mode in LINK_MODES:
            selected=mode==current
            button=tk.Button(mode_box,text=f"{mode}\n{descriptions[mode]}",command=lambda value=mode:self._set_layout_link_mode(value),
                             bg=ACCENT if selected else PANEL2,fg="white" if selected else TEXT,
                             activebackground="#927aff" if selected else "#252b3b",activeforeground="white",
                             relief="flat",font=("Segoe UI Semibold",8),padx=5,pady=8,cursor="hand2",wraplength=82)
            button.pack(side="left",expand=True,fill="x",padx=(0 if mode==LINK_EXTEND else 4,0))
        if not devices:
            tk.Label(self.page,text="点击“扫描并连接”后，设备会自动出现在左侧画布。",bg=PANEL2,fg=MUTED,
                     font=("Segoe UI",9),padx=12,pady=16,wraplength=275,justify="left").pack(fill="x",pady=14)
            return
        tk.Label(self.page,text="设备",bg=BG,fg=MUTED,font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(14,2))
        if current!=LINK_INDEPENDENT:
            tk.Label(self.page,text="扩展/复制模式由左侧功能页面统一切换，不需要逐台分配模式。",bg=BG,fg="#687187",font=("Segoe UI",8),wraplength=290,justify="left").pack(anchor="w",pady=(0,4))
        for item in sorted(devices,key=lambda row:int(row.get("number",99))):
            device_id=str(item.get("id")); device=self.launchpads.get(device_id); online=bool(device and device.connected)
            card=self._card(); header=tk.Frame(card,bg=PANEL2); header.pack(fill="x")
            tk.Label(header,text=f"LP {item.get('number',1)}",bg=PANEL2,fg=TEXT,font=("Segoe UI Semibold",12)).pack(side="left")
            tk.Label(header,text="● 已连接" if online else "○ 未连接",bg=PANEL2,fg=GOOD if online else MUTED,font=("Segoe UI",8)).pack(side="left",padx=8)
            ttk.Button(header,text="选中",command=lambda did=device_id:self._select_layout_device(did)).pack(side="right")
            model_name=device.model.name if device else next((model.name for model in MODELS if model.key==item.get("model")),"自动识别")
            tk.Label(card,text=f"{model_name} · 位置 ({item.get('x',0)}, {item.get('y',0)})",bg=PANEL2,fg=MUTED,font=("Segoe UI",8)).pack(anchor="w",pady=(5,6))
            if current==LINK_INDEPENDENT:
                row=tk.Frame(card,bg=PANEL2); row.pack(fill="x",pady=(2,6))
                tk.Label(row,text="运行功能",bg=PANEL2,fg=MUTED,font=("Segoe UI",8)).pack(side="left")
                variable=tk.StringVar(value=item.get("mode","性能监控"))
                combo=ttk.Combobox(row,textvariable=variable,state="readonly",values=MODE_SOURCES,width=12)
                combo.pack(side="right"); combo.bind("<<ComboboxSelected>>",lambda _e,did=device_id,var=variable:self._set_device_mode(did,var.get()))
            ttk.Button(card,text="在实机显示编号",command=lambda did=device_id:self._identify_device(did)).pack(fill="x")
        self._sync_canvas_preview()

    def _set_layout_link_mode(self,mode):
        if mode not in LINK_MODES:return
        self.multi_cfg["link_mode"]=mode; self.settings_store.save()
        self._redispatch_frames(); self._show_mode("布局设置")
        self.set_status(f"联动方式已切换为 {mode}")

    def _set_device_mode(self,device_id,mode):
        if mode not in MODE_SOURCES:return
        item=next((row for row in self.multi_cfg.get("devices",[]) if str(row.get("id"))==str(device_id)),None)
        if not item:return
        item["mode"]=mode; self.settings_store.save(); self._redispatch_frames(); self._sync_canvas_preview()
        self.set_status(f"LP {item.get('number',1)} 已分配到 {mode}")

    def _select_layout_device(self,device_id):
        self.layout_selected_id=str(device_id); self.pad_canvas.selected_device=str(device_id); self.pad_canvas.draw()

    def _identify_device(self,device_id):
        item=next((row for row in self.multi_cfg.get("devices",[]) if str(row.get("id"))==str(device_id)),None)
        device=self.launchpads.get(str(device_id))
        if not item or not device or not device.connected:
            self.set_status("设备尚未连接，请先扫描并连接"); return
        device.set_frame(number_frame(item.get("number",1)),force=True); self.after(1800,self._redispatch_frames)
        self.set_status(f"正在用灯光显示 LP {item.get('number',1)}")

    def _page_performance(self):
        self._page_title("性能监控","负载映射到 8×8 灯柱；右侧圆键显示当前最高硬件温度。")
        self._macro_control_switch()
        self.metric_labels={}
        metric_box=tk.Frame(self.page,bg=PANEL2,padx=10,pady=8); metric_box.pack(fill="x",pady=5)
        for key in ["CPU","RAM","GPU","磁盘","网络 MB/s","磁盘 MB/s"]:
            i=len(self.metric_labels); c=tk.Frame(metric_box,bg=PANEL2,padx=5,pady=5); c.grid(row=i//2,column=i%2,sticky="ew",padx=2,pady=1)
            tk.Label(c,text=key,bg=PANEL2,fg=MUTED,font=("Segoe UI",8)).pack(anchor="w")
            lab=tk.Label(c,text="--",bg=PANEL2,fg=TEXT,font=("Segoe UI Semibold",12)); lab.pack(anchor="w"); self.metric_labels[key]=lab
        metric_box.grid_columnconfigure((0,1),weight=1,uniform="metric")
        tk.Label(self.page,text="硬件温度",bg=BG,fg=MUTED,font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(12,3))
        temp_box=tk.Frame(self.page,bg=PANEL2,padx=10,pady=8); temp_box.pack(fill="x",pady=4)
        self.temp_labels={}
        for i,key in enumerate(["CPU","GPU","主板","存储"]):
            c=tk.Frame(temp_box,bg=PANEL2,padx=5,pady=5); c.grid(row=i//2,column=i%2,sticky="ew",padx=2,pady=1)
            tk.Label(c,text=f"{key} 温度",bg=PANEL2,fg=MUTED,font=("Segoe UI",8)).pack(anchor="w")
            lab=tk.Label(c,text="检测中…",bg=PANEL2,fg=MUTED,font=("Segoe UI Semibold",12)); lab.pack(anchor="w"); self.temp_labels[key]=lab
        temp_box.grid_columnconfigure((0,1),weight=1,uniform="temp")
        self.temp_hint=tk.Label(self.page,text="部分 CPU/主板传感器需要管理员权限",bg=BG,fg="#5f687c",font=("Segoe UI",8)); self.temp_hint.pack(anchor="w",pady=(3,2))
        ttk.Button(self.page,text="以管理员权限重启读取完整温度",command=self._restart_admin).pack(fill="x",pady=(3,6))
        ttk.Button(self.page,text="开始实时监控",style="Accent.TButton",command=self._start_perf).pack(fill="x",pady=(6,6))
        ttk.Button(self.page,text="停止",command=lambda:self._stop_mode("性能监控",True)).pack(fill="x")

    def _start_perf(self):
        self._activate_mode("性能监控")
        self.running_perf=True; self.set_status("性能监控运行中 · 2 Hz"); self._perf_tick()

    def _perf_tick(self):
        if not self.running_perf or "性能监控" not in self.active_modes: return
        stats=self.performance.sample()
        self.last_perf_stats=stats
        if self.mode=="性能监控":
            for k,l in getattr(self,"metric_labels",{}).items():
                v=stats[k]; l.configure(text="不可用" if v is None else (f"{v:.1f}%" if k in ["CPU","RAM","GPU","磁盘"] else f"{v:.1f}"))
            temps=stats.get("temperatures",{})
            for k,l in getattr(self,"temp_labels",{}).items():
                v=temps.get(k)
                if isinstance(v,(int,float)):
                    color=BAD if v>=85 else "#fbbf24" if v>=70 else GOOD
                    l.configure(text=f"{v:.1f} °C",fg=color)
                else:
                    l.configure(text="需权限 / 无传感器",fg=MUTED)
        self.apply_frame(self.performance.frame(stats,self.palette_var.get(),self.brightness.get()/100,self._output_size("性能监控")),"性能监控")
        self.after(500,self._perf_tick)

    def _restart_admin(self):
        try:
            arguments="--admin-restart" if FROZEN else f'"{Path(__file__).resolve()}" --admin-restart'
            result=ctypes.windll.shell32.ShellExecuteW(None,"runas",sys.executable,
                                                       arguments,str(ROOT),1)
            if result>32:self._close()
            else:messagebox.showerror("启动失败",f"无法获取管理员权限（代码 {result}）")
        except Exception as exc:messagebox.showerror("启动失败",str(exc))

    def _page_macros(self):
        self._page_title("宏按键","点选画布上的按键，为它设置电脑操作与独立颜色；按下真机按键立即执行。")
        c=self._card(); self.pad_name=tk.Label(c,text="当前按键：81",bg=PANEL2,fg=TEXT,font=("Segoe UI Semibold",12)); self.pad_name.pack(anchor="w")
        tk.Label(self.page,text="操作类型",bg=BG,fg=MUTED).pack(anchor="w",pady=(12,4))
        self.action_var=tk.StringVar(value="热键")
        ttk.Combobox(self.page,textvariable=self.action_var,state="readonly",values=["热键","输入文字","打开文件/程序","打开网址","执行命令","PowerShell","媒体控制","按键序列","鼠标操作","系统操作","设置音量","组合动作"]).pack(fill="x")
        tk.Label(self.page,text="内容",bg=BG,fg=MUTED).pack(anchor="w",pady=(12,4))
        self.macro_value=tk.StringVar(); ttk.Entry(self.page,textvariable=self.macro_value).pack(fill="x")
        tk.Label(self.page,text="示例：CTRL+SHIFT+S；PLAY；左键/右键/双击；锁定电脑/截图/任务管理器；音量 0–100。组合动作每行使用 hotkey:、text:、wait:、open:、url:、mouse:。",bg=BG,fg="#5f687c",font=("Segoe UI",8),wraplength=310,justify="left").pack(anchor="w",pady=4)
        self.macro_color="#7c5cff"
        ttk.Button(self.page,text="选择此按键颜色",command=self._pick_macro_color).pack(fill="x",pady=(12,6))
        ttk.Button(self.page,text="保存按键",style="Accent.TButton",command=self._save_macro).pack(fill="x",pady=6)
        macro_row=tk.Frame(self.page,bg=BG); macro_row.pack(fill="x")
        ttk.Button(macro_row,text="测试执行",command=self._test_macro).pack(side="left",expand=True,fill="x")
        ttk.Button(macro_row,text="清除当前按键",command=self._clear_macro).pack(side="left",expand=True,fill="x",padx=(5,0))
        macro_mode_row=tk.Frame(self.page,bg=BG); macro_mode_row.pack(fill="x",pady=(12,0))
        ttk.Button(macro_mode_row,text="启用宏按键灯光",command=self._start_macros).pack(side="left",expand=True,fill="x")
        ttk.Button(macro_mode_row,text="停止",command=lambda:self._stop_mode("宏按键",True)).pack(side="left",fill="x",padx=(5,0))
        self._load_macro_form(*self.selected_pad)

    def _macro_key(self,x,y):
        return f"pad:{x}:{y}"

    def _macro_aliases(self,x,y):
        aliases=[]
        for model in MODELS:
            number=model.address(x,y)
            if number is not None:aliases.append(f"{model.key}:{number}")
        mk2_number=next(model.address(x,y) for model in MODELS if model.key=="mk2")
        if mk2_number is not None:aliases.append(str(mk2_number))
        return aliases

    def _macro_get(self,x,y):
        macros=self.settings_store.data["macros"]
        macro=macros.get(self._macro_key(x,y))
        if macro:return macro
        return next((macros[key] for key in self._macro_aliases(x,y) if key in macros),{})

    def _load_macro_form(self,x,y):
        self.selected_pad=(x,y); macro=self._macro_get(x,y)
        if hasattr(self,"pad_name"): self.pad_name.configure(text=f"当前按键：{self.lp.pad_label(x,y)}")
        if hasattr(self,"action_var"): self.action_var.set(macro.get("action","热键")); self.macro_value.set(macro.get("value","")); self.macro_color=macro.get("color","#7c5cff")

    def _pick_macro_color(self):
        value=colorchooser.askcolor(self.macro_color,title="按键颜色")[1]
        if value: self.macro_color=value

    def _save_macro(self):
        key=self._macro_key(*self.selected_pad); macros=self.settings_store.data["macros"]
        macros[key]={"action":self.action_var.get(),"value":self.macro_value.get().strip(),"color":self.macro_color}
        for alias in self._macro_aliases(*self.selected_pad):macros.pop(alias,None)
        self.settings_store.save()
        if "宏按键" in self.active_modes:self._render_macro_profile()
        self.set_status(f"按键 {self.lp.pad_label(*self.selected_pad)} 已保存")

    def _test_macro(self):
        macro=self._macro_get(*self.selected_pad)
        if macro: self.macro_exec.execute(macro)

    def _clear_macro(self):
        key=self._macro_key(*self.selected_pad); label=self.lp.pad_label(*self.selected_pad)
        if not messagebox.askyesno("清除宏按键",f"确定清除按键 {label} 的功能和独立颜色吗？",parent=self):return
        macros=self.settings_store.data["macros"]; macros.pop(key,None)
        for alias in self._macro_aliases(*self.selected_pad):macros.pop(alias,None)
        self.settings_store.save(); self.action_var.set("热键"); self.macro_value.set(""); self.macro_color="#7c5cff"
        if "宏按键" in self.active_modes:self._render_macro_profile()
        self.set_status(f"按键 {label} 已清除")

    def _start_macros(self):
        self._activate_mode("宏按键"); self._render_macro_profile(); self.set_status("宏按键模式运行中")

    def _render_macro_profile(self):
        frame={xy:(0,0,0) for xy in self.lp.pads}
        for xy in self.lp.pads:
            m=self._macro_get(*xy)
            if m:
                h=m.get("color","#7c5cff").lstrip("#"); frame[xy]=tuple(int(h[i:i+2],16) for i in (0,2,4))
        self.apply_frame(frame,"宏按键")

    def _page_video(self):
        self._page_title("视频像素播放器","播放列表、拖动定位、变速、循环与实时像素滤镜。")
        self._macro_control_switch()
        saved=self.settings_store.data["detail_params"]["video"]
        self.video_list=tk.Listbox(self.page,height=4,bg=PANEL2,fg=TEXT,selectbackground=ACCENT,
                                   relief="flat",highlightthickness=0,font=("Segoe UI",9))
        self.video_list.pack(fill="x"); self.video_list.bind("<Double-Button-1>",lambda _e:self._start_video())
        for p in self.video_playlist:self.video_list.insert("end",Path(p).name)
        if 0<=self.video_index<len(self.video_playlist):self.video_list.selection_set(self.video_index)
        row=tk.Frame(self.page,bg=BG); row.pack(fill="x",pady=(6,8))
        ttk.Button(row,text="＋ 添加",command=self._choose_video).pack(side="left",expand=True,fill="x")
        ttk.Button(row,text="清空",command=self._clear_video_list).pack(side="left",expand=True,fill="x",padx=(5,0))
        self.video_progress=tk.DoubleVar(); scale=ttk.Scale(self.page,from_=0,to=1000,variable=self.video_progress,orient="horizontal")
        scale.pack(fill="x",pady=(4,0)); scale.bind("<ButtonPress-1>",lambda _e:setattr(self,"video_seeking",True)); scale.bind("<ButtonRelease-1>",self._seek_video)
        self.video_time=tk.Label(self.page,text="00:00 / 00:00",bg=BG,fg=MUTED,font=("Segoe UI",8)); self.video_time.pack(anchor="e")
        transport=tk.Frame(self.page,bg=BG); transport.pack(fill="x",pady=6)
        ttk.Button(transport,text="⏮ 上一曲",command=lambda:self._advance_video(-1)).pack(side="left",expand=True,fill="x")
        self.video_pause_btn=ttk.Button(transport,text="▶ 播放",style="Accent.TButton",command=self._video_pause); self.video_pause_btn.pack(side="left",expand=True,fill="x",padx=5)
        ttk.Button(transport,text="下一曲 ⏭",command=lambda:self._advance_video(1)).pack(side="left",expand=True,fill="x")
        options=tk.Frame(self.page,bg=BG); options.pack(fill="x",pady=(3,8))
        self.video_rate=tk.StringVar(value=saved.get("rate","1.00×")); rate=ttk.Combobox(options,textvariable=self.video_rate,state="readonly",width=8,values=["0.50×","0.75×","1.00×","1.25×","1.50×","2.00×","3.00×"]); rate.pack(side="left"); rate.bind("<<ComboboxSelected>>",lambda _e:(self.video.set_rate(self._rate(self.video_rate.get())),self._schedule_param_save("video")))
        self.video_loop=tk.StringVar(value=saved.get("loop","列表循环")); loop=ttk.Combobox(options,textvariable=self.video_loop,state="readonly",width=11,values=["不循环","单曲循环","列表循环"]); loop.pack(side="right"); loop.bind("<<ComboboxSelected>>",lambda _e:self._schedule_param_save("video"))
        tk.Label(self.page,text="像素滤镜",bg=BG,fg=MUTED).pack(anchor="w",pady=(8,3))
        self.video_effect=tk.StringVar(value=saved.get("effect","原色视频")); effect=ttk.Combobox(self.page,textvariable=self.video_effect,state="readonly",values=["原色视频","亮度热图","边缘轮廓","单色辉光","镜像万花筒","像素故障"]); effect.pack(fill="x"); effect.bind("<<ComboboxSelected>>",lambda _e:self._update_video_effect())
        self._build_preset_controls("video")
        self.video_fps=tk.IntVar(value=saved.get("fps",20)); self.video_vars={}
        self._parameter_scale("输出帧率",self.video_fps,5,30,lambda:self._update_video_effect(),".0f")
        for name,label,value,lo,hi in [("saturation","饱和度",1.25,0,2),("contrast","对比度",1.0,.2,2.5),("gamma","伽马",1.0,.25,2.5),("edge_threshold","边缘阈值",70,10,180)]:
            var=tk.DoubleVar(value=saved.get(name,value)); self.video_vars[name]=var; self._parameter_scale(label,var,lo,hi,lambda:self._update_video_effect(),".2f" if hi<10 else ".0f")
        ttk.Button(self.page,text="停止",command=lambda:self._stop_mode("视频播放",True)).pack(fill="x",pady=(10,18))

    def _choose_video(self):
        paths=self._pick_files("添加视频","视频文件|*.mp4;*.avi;*.mov;*.mkv;*.webm|所有文件|*.*")
        for p in paths:
            if p not in self.video_playlist:self.video_playlist.append(p); self.video_list.insert("end",Path(p).name)
        self.settings_store.data["video_playlist"]=self.video_playlist; self.settings_store.save()
        if paths and self.video_index<0:self.video_index=0; self.video_list.selection_set(0)

    def _start_video(self):
        sel=self.video_list.curselection() if hasattr(self,"video_list") else ()
        if sel:self.video_index=sel[0]
        if not (0<=self.video_index<len(self.video_playlist)):return messagebox.showinfo("Launchpad Studio","请先添加视频。")
        self._activate_mode("视频播放")
        self.video_path=self.video_playlist[self.video_index]
        self.video_list.selection_clear(0,"end"); self.video_list.selection_set(self.video_index); self.video_list.see(self.video_index)
        params=self._video_params(); self.video.start(self.video_path,self.video_fps.get(),self.brightness.get()/100,
              params["saturation"],self._rate(self.video_rate.get()),0,self.video_effect.get(),params,self._output_size("视频播放"))
        self.video_pause_btn.configure(text="⏸ 暂停")

    def _clear_video_list(self):
        self.video.stop(); self.video_playlist.clear(); self.video_index=-1; self.video_list.delete(0,"end"); self.settings_store.data["video_playlist"]=[]; self.settings_store.save()

    def _video_pause(self):
        if not self.video.thread or not self.video.thread.is_alive():return self._start_video()
        paused=self.video.pause_toggle(); self.video_pause_btn.configure(text="▶ 继续" if paused else "⏸ 暂停")

    def _advance_video(self,step,auto=False):
        if not self.video_playlist:return
        mode=self.video_loop.get() if hasattr(self,"video_loop") else "不循环"
        if auto and mode=="单曲循环":return self._start_video()
        target=self.video_index+step
        if target<0 or target>=len(self.video_playlist):
            if mode=="列表循环":target%=len(self.video_playlist)
            elif auto:
                self.set_status("播放列表结束")
                if hasattr(self,"video_pause_btn"):self.video_pause_btn.configure(text="▶ 播放")
                return
            else:target=max(0,min(len(self.video_playlist)-1,target))
        self.video_index=target
        if hasattr(self,"video_list"):
            self.video_list.selection_clear(0,"end"); self.video_list.selection_set(target); self.video_list.see(target)
        self._start_video()

    def _video_progress(self,pos,duration):
        self._queue_ui(("video_progress",pos,duration))

    def _video_finished(self):self._queue_ui(("video_finished",))

    def _seek_video(self,_event=None):
        self.video_seeking=False
        if self.video_duration:self.video.seek(self.video_progress.get()/1000*self.video_duration)

    def _video_params(self):
        p={k:v.get() for k,v in getattr(self,"video_vars",{}).items()}; p["brightness"]=self.brightness.get()/100
        h=self.custom_color.lstrip("#"); p["tint"]=tuple(int(h[i:i+2],16) for i in (0,2,4)); return p

    def _update_video_effect(self):
        if hasattr(self,"video_effect"):
            self.video.set_effect(self.video_effect.get(),self._video_params()); self.video.set_output_size(self._output_size("视频播放"))
        self._schedule_param_save("video")

    def _page_music(self):
        self._page_title("音乐灯光播放器","音频播放、变速与灯光采样使用同一时间轴，拖动后保持同步。")
        self._macro_control_switch()
        saved=self.settings_store.data["detail_params"]["music"]
        self.audio_list=tk.Listbox(self.page,height=4,bg=PANEL2,fg=TEXT,selectbackground=ACCENT,relief="flat",highlightthickness=0,font=("Segoe UI",9)); self.audio_list.pack(fill="x"); self.audio_list.bind("<Double-Button-1>",lambda _e:self._start_music())
        for p in self.audio_playlist:self.audio_list.insert("end",Path(p).name)
        if 0<=self.audio_index<len(self.audio_playlist):self.audio_list.selection_set(self.audio_index)
        row=tk.Frame(self.page,bg=BG); row.pack(fill="x",pady=(6,8)); ttk.Button(row,text="＋ 添加",command=self._choose_audio).pack(side="left",expand=True,fill="x"); ttk.Button(row,text="清空",command=self._clear_audio_list).pack(side="left",expand=True,fill="x",padx=(5,0))
        self.analysis_label=tk.Label(self.page,text="BPM --  ·  情绪 --  ·  能量 --",bg=BG,fg=MUTED,font=("Segoe UI",9)); self.analysis_label.pack(anchor="w",pady=8)
        self.audio_progress=tk.DoubleVar(); scale=ttk.Scale(self.page,from_=0,to=1000,variable=self.audio_progress,orient="horizontal"); scale.pack(fill="x"); scale.bind("<ButtonPress-1>",lambda _e:setattr(self,"audio_seeking",True)); scale.bind("<ButtonRelease-1>",self._seek_audio)
        self.audio_time=tk.Label(self.page,text="00:00 / 00:00",bg=BG,fg=MUTED,font=("Segoe UI",8)); self.audio_time.pack(anchor="e")
        transport=tk.Frame(self.page,bg=BG); transport.pack(fill="x",pady=6); ttk.Button(transport,text="⏮ 上一曲",command=lambda:self._advance_audio(-1)).pack(side="left",expand=True,fill="x"); self.audio_pause_btn=ttk.Button(transport,text="▶ 播放",style="Accent.TButton",command=self._audio_pause); self.audio_pause_btn.pack(side="left",expand=True,fill="x",padx=5); ttk.Button(transport,text="下一曲 ⏭",command=lambda:self._advance_audio(1)).pack(side="left",expand=True,fill="x")
        options=tk.Frame(self.page,bg=BG); options.pack(fill="x",pady=(3,8)); self.audio_rate=tk.StringVar(value=saved.get("rate","1.00×")); rate=ttk.Combobox(options,textvariable=self.audio_rate,state="readonly",width=8,values=["0.50×","0.75×","1.00×","1.25×","1.50×","2.00×","3.00×"]); rate.pack(side="left"); rate.bind("<<ComboboxSelected>>",lambda _e:(self.music and self.music.set_rate(self._rate(self.audio_rate.get())),self._schedule_param_save("music"))); self.audio_loop=tk.StringVar(value=saved.get("loop","列表循环")); loop=ttk.Combobox(options,textvariable=self.audio_loop,state="readonly",width=11,values=["不循环","单曲循环","列表循环"]); loop.pack(side="right"); loop.bind("<<ComboboxSelected>>",lambda _e:self._schedule_param_save("music"))
        self.audio_volume=tk.DoubleVar(value=saved.get("volume",85)); self._parameter_scale("播放音量 %",self.audio_volume,0,100,self._music_volume_changed,".0f")
        tk.Label(self.page,text="灯光编排",bg=BG,fg=MUTED).pack(anchor="w",pady=(8,4))
        self.music_style=tk.StringVar(value=saved.get("style","频谱")); style=ttk.Combobox(self.page,textvariable=self.music_style,state="readonly",values=self._visual_styles()); style.pack(fill="x"); style.bind("<<ComboboxSelected>>",lambda _e:self._update_music_visual())
        self._build_preset_controls("music")
        self.music_visual_vars=self._build_visual_parameters("music",lambda:self._update_music_visual())
        ttk.Button(self.page,text="停止",command=lambda:self._stop_mode("音乐演示",True)).pack(fill="x",pady=(10,18))

    def _choose_audio(self):
        paths=self._pick_files("添加音频","音频文件|*.wav;*.mp3;*.ogg;*.flac;*.aiff|所有文件|*.*")
        for p in paths:
            if p not in self.audio_playlist:self.audio_playlist.append(p); self.audio_list.insert("end",Path(p).name)
        self.settings_store.data["audio_playlist"]=self.audio_playlist; self.settings_store.save()
        if not paths:return
        if self.audio_index<0:self.audio_index=0; self.audio_list.selection_set(0)
        p=self.audio_playlist[self.audio_index]; self.audio_path=p; self.analysis_label.configure(text="正在分析…")
        def work():
            try:
                if not self.music:self.music=MusicShow(lambda frame:self.submit_frame(frame,"音乐演示"),self.set_status,self._audio_progress,self._audio_finished)
                a=self.music.analyse(p); self.after(0,lambda:self.analysis_label.configure(text=f"BPM {a.bpm}  ·  {a.mood}  ·  {a.genre}\n能量 {a.energy*100:.0f}%"))
            except Exception as e:self.after(0,lambda err=str(e):self.analysis_label.configure(text=f"分析失败：{err}"))
        threading.Thread(target=work,daemon=True).start()

    def _start_music(self):
        sel=self.audio_list.curselection() if hasattr(self,"audio_list") else ()
        if sel:self.audio_index=sel[0]
        if not (0<=self.audio_index<len(self.audio_playlist)):return messagebox.showinfo("Launchpad Studio","请先添加音频。")
        self._activate_mode("音乐演示")
        self.audio_path=self.audio_playlist[self.audio_index]; self.audio_list.selection_clear(0,"end"); self.audio_list.selection_set(self.audio_index); self.audio_list.see(self.audio_index)
        try:
            if not self.music:self.music=MusicShow(lambda frame:self.submit_frame(frame,"音乐演示"),self.set_status,self._audio_progress,self._audio_finished)
            a=self.music.analyse(self.audio_path); self.analysis_label.configure(text=f"BPM {a.bpm}  ·  {a.mood}  ·  {a.genre}\n能量 {a.energy*100:.0f}%")
            self.music.set_volume(self.audio_volume.get()/100)
            self.music.start(self.audio_path,self.music_style.get(),self.palette_var.get(),self.brightness.get()/100,self._visual_params(self.music_visual_vars),0,self._rate(self.audio_rate.get()),self.audio_loop.get()=="单曲循环",self._output_size("音乐演示"))
            self.audio_pause_btn.configure(text="⏸ 暂停")
        except Exception as e:messagebox.showerror("音频播放失败",str(e))

    def _clear_audio_list(self):
        if self.music:self.music.stop()
        self.audio_playlist.clear(); self.audio_index=-1; self.audio_list.delete(0,"end"); self.settings_store.data["audio_playlist"]=[]; self.settings_store.save()

    def _audio_pause(self):
        if not self.music or not self.music.worker or not self.music.worker.is_alive():return self._start_music()
        paused=self.music.pause_toggle(); self.audio_pause_btn.configure(text="▶ 继续" if paused else "⏸ 暂停")

    def _advance_audio(self,step,auto=False):
        if not self.audio_playlist:return
        mode=self.audio_loop.get() if hasattr(self,"audio_loop") else "不循环"
        if auto and mode=="单曲循环":return self._start_music()
        target=self.audio_index+step
        if target<0 or target>=len(self.audio_playlist):
            if mode=="列表循环":target%=len(self.audio_playlist)
            elif auto:
                self.set_status("播放列表结束")
                if self.music:self.music.stop()
                if hasattr(self,"audio_pause_btn"):self.audio_pause_btn.configure(text="▶ 播放")
                return
            else:target=max(0,min(len(self.audio_playlist)-1,target))
        self.audio_index=target
        if hasattr(self,"audio_list"):
            self.audio_list.selection_clear(0,"end"); self.audio_list.selection_set(target); self.audio_list.see(target)
        self._start_music()

    def _audio_progress(self,pos,duration):
        self._queue_ui(("audio_progress",pos,duration))

    def _audio_finished(self):self._queue_ui(("audio_finished",))

    def _seek_audio(self,_event=None):
        self.audio_seeking=False
        if self.music and self.audio_duration:self.music.seek(self.audio_progress.get()/1000*self.audio_duration)

    def _update_music_visual(self):
        if self.music and hasattr(self,"music_visual_vars"):self.music.set_visual(self.music_style.get(),self.palette_var.get(),self.brightness.get()/100,self._visual_params(self.music_visual_vars),self._output_size("音乐演示"))
        self._schedule_param_save("music")

    def _music_volume_changed(self):
        if self.music:self.music.set_volume(self.audio_volume.get()/100)
        self._schedule_param_save("music")

    @staticmethod
    def _visual_styles():
        return ["频谱","对称频谱","波形","脉冲","涟漪","星云","雨幕","火焰","隧道","棋盘"]

    @staticmethod
    def _fmt_time(seconds):
        seconds=max(0,int(seconds or 0)); return f"{seconds//60:02d}:{seconds%60:02d}"

    @staticmethod
    def _rate(text):
        try:return float(text.replace("×",""))
        except Exception:return 1.0

    def _pick_files(self,title,filter_text):
        # Keep Windows shell/codec extensions outside the main process. A broken
        # shell extension previously raised a fatal COM exception in Tk's dialog.
        safe_title=title.replace("'","''"); safe_filter=filter_text.replace("'","''")
        script=("[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$d=New-Object System.Windows.Forms.OpenFileDialog;"
                f"$d.Title='{safe_title}';$d.Filter='{safe_filter}';$d.Multiselect=$true;"
                "if($d.ShowDialog() -eq 'OK'){ConvertTo-Json -Compress -InputObject ([string[]]$d.FileNames)}")
        try:
            flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
            raw=subprocess.check_output(["powershell","-STA","-NoProfile","-WindowStyle","Hidden","-Command",script],
                                        text=True,encoding="utf-8",errors="replace",creationflags=flags)
            value=__import__("json").loads(raw.strip()) if raw.strip() else []
            return [value] if isinstance(value,str) else list(value)
        except Exception as exc:
            logging.error("File picker failed",exc_info=True); messagebox.showerror("文件选择失败",str(exc)); return []

    def _parameter_scale(self,label,var,lo,hi,on_change,fmt=".2f"):
        row=tk.Frame(self.page,bg=BG); row.pack(fill="x",pady=(6,0))
        tk.Label(row,text=label,bg=BG,fg=MUTED,font=("Segoe UI",8)).pack(side="left")
        value=tk.Label(row,text=format(var.get(),fmt),bg=BG,fg=TEXT,font=("Segoe UI",8)); value.pack(side="right")
        def changed(_v=None):
            value.configure(text=format(var.get(),fmt)); on_change()
        var.trace_add("write",lambda *_args:changed())
        ttk.Scale(self.page,from_=lo,to=hi,variable=var,orient="horizontal").pack(fill="x")

    def _build_visual_parameters(self,mode,on_change):
        tk.Label(self.page,text="灯效细节参数",bg=BG,fg=MUTED,font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(12,2))
        specs=[("freq_min","频谱下限 Hz",40,20,1000,".0f"),("freq_max","频谱上限 Hz",16000,1000,22000,".0f"),
               ("loud_min","响度下限 dB",-55,-80,-20,".0f"),("loud_max","响度上限 dB",-6,-30,0,".0f"),
               ("sensitivity","灵敏度",1.0,.1,4,".2f"),("threshold","噪声阈值",.012,0,.2,".3f"),
               ("speed","动画速度",1.0,.2,3,".2f"),("spread","扩散强度",1.0,.3,2.5,".2f")]
        variables={}
        saved=self.settings_store.data["detail_params"].get(mode,{})
        for key,label,value,lo,hi,fmt in specs:
            variables[key]=tk.DoubleVar(value=saved.get(key,value)); self._parameter_scale(label,variables[key],lo,hi,on_change,fmt)
        return variables

    @staticmethod
    def _visual_params(variables):
        return {k:v.get() for k,v in variables.items()}

    def _detail_snapshot(self,mode):
        if mode=="video":
            values={k:v.get() for k,v in getattr(self,"video_vars",{}).items()}
            if hasattr(self,"video_fps"):values["fps"]=self.video_fps.get()
            if hasattr(self,"video_effect"):values["effect"]=self.video_effect.get()
            if hasattr(self,"video_rate"):values["rate"]=self.video_rate.get()
            if hasattr(self,"video_loop"):values["loop"]=self.video_loop.get()
            return values
        variables=getattr(self,f"{mode}_visual_vars",{})
        values=self._visual_params(variables)
        style=getattr(self,f"{mode}_style",None)
        if style:values["style"]=style.get()
        if mode=="music" and hasattr(self,"audio_volume"):
            values.update(volume=self.audio_volume.get(),rate=self.audio_rate.get(),loop=self.audio_loop.get())
        return values

    def _save_detail_now(self,mode):
        values=self._detail_snapshot(mode)
        if values:
            self.settings_store.data["detail_params"][mode].update(values)
            self.settings_store.save()

    def _schedule_param_save(self,mode):
        if self._param_save_job:
            try:self.after_cancel(self._param_save_job)
            except Exception:pass
        self._param_save_job=self.after(300,lambda:self._finish_param_save(mode))

    def _finish_param_save(self,mode):
        self._param_save_job=None; self._save_detail_now(mode)

    def _apply_detail_snapshot(self,mode,values):
        variables=getattr(self,"video_vars",{}) if mode=="video" else getattr(self,f"{mode}_visual_vars",{})
        for key,var in variables.items():
            if key in values:
                try:var.set(float(values[key]))
                except (TypeError,ValueError):pass
        if mode=="video":
            if "fps" in values:self.video_fps.set(int(float(values["fps"])))
            if "effect" in values and values["effect"] in ["原色视频","亮度热图","边缘轮廓","单色辉光","镜像万花筒","像素故障"]:self.video_effect.set(values["effect"])
            if values.get("rate") in ["0.50×","0.75×","1.00×","1.25×","1.50×","2.00×","3.00×"]:self.video_rate.set(values["rate"])
            if values.get("loop") in ["不循环","单曲循环","列表循环"]:self.video_loop.set(values["loop"])
            self._update_video_effect()
        else:
            style=getattr(self,f"{mode}_style",None)
            if style and values.get("style") in self._visual_styles():style.set(values["style"])
            if mode=="music":
                if "volume" in values:self.audio_volume.set(float(values["volume"]))
                if values.get("rate") in ["0.50×","0.75×","1.00×","1.25×","1.50×","2.00×","3.00×"]:self.audio_rate.set(values["rate"])
                if values.get("loop") in ["不循环","单曲循环","列表循环"]:self.audio_loop.set(values["loop"])
            (self._update_music_visual if mode=="music" else self._update_live_visual)()
        self._save_detail_now(mode)

    def _preset_group(self,mode):
        return "video" if mode=="video" else "audio"

    def _preset_names(self,mode):
        presets=self.settings_store.data["presets"][self._preset_group(mode)]
        recent=self.settings_store.data["recent_presets"].get(mode,[])
        return recent+[name for name in presets if name not in recent]

    def _build_preset_controls(self,mode):
        tk.Label(self.page,text="参数预设",bg=BG,fg=MUTED,font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(12,3))
        var=tk.StringVar(); combo=ttk.Combobox(self.page,textvariable=var,state="readonly",values=self._preset_names(mode))
        combo.pack(fill="x",pady=(0,5))
        if combo["values"]:combo.current(0)
        if not hasattr(self,"preset_vars"):self.preset_vars={}
        self.preset_vars[mode]=var
        row=tk.Frame(self.page,bg=BG); row.pack(fill="x")
        ttk.Button(row,text="保存预设",command=lambda:self._save_preset(mode)).pack(side="left",expand=True,fill="x")
        ttk.Button(row,text="加载",command=lambda:self._load_preset(mode)).pack(side="left",expand=True,fill="x",padx=4)
        ttk.Button(row,text="默认",command=lambda:self._reset_detail(mode)).pack(side="left",expand=True,fill="x")
        row2=tk.Frame(self.page,bg=BG); row2.pack(fill="x",pady=(5,0))
        ttk.Button(row2,text="复制参数",command=lambda:self._copy_detail(mode)).pack(side="left",expand=True,fill="x")
        ttk.Button(row2,text="粘贴参数",command=lambda:self._paste_detail(mode)).pack(side="left",expand=True,fill="x",padx=(5,0))

    def _touch_recent(self,mode,name):
        recent=self.settings_store.data["recent_presets"].setdefault(mode,[])
        recent[:]=[name]+[n for n in recent if n!=name][:4]

    def _save_preset(self,mode):
        name=simpledialog.askstring("保存参数预设","预设名称：",parent=self)
        if not name or not name.strip():return
        name=name.strip(); group=self._preset_group(mode)
        self.settings_store.data["presets"][group][name]=self._detail_snapshot(mode)
        self._touch_recent(mode,name); self.settings_store.save()
        self.preset_vars[mode].set(name); self.set_status(f"参数预设“{name}”已保存")

    def _load_preset(self,mode):
        name=self.preset_vars.get(mode,tk.StringVar()).get()
        values=self.settings_store.data["presets"][self._preset_group(mode)].get(name)
        if not values:return self.set_status("请先选择一个参数预设")
        self._apply_detail_snapshot(mode,values); self._touch_recent(mode,name); self.settings_store.save()
        self.set_status(f"已加载参数预设“{name}”")

    def _reset_detail(self,mode):
        defaults=dict(VIDEO_DETAIL_DEFAULTS if mode=="video" else AUDIO_DETAIL_DEFAULTS)
        if mode=="music":defaults.update(style="频谱",volume=85,rate="1.00×",loop="列表循环")
        elif mode=="live":defaults.update(style="星云")
        else:defaults.update(rate="1.00×",loop="列表循环")
        self._apply_detail_snapshot(mode,defaults); self.set_status("细节参数已恢复默认")

    def _copy_detail(self,mode):
        payload={"format":"launchpad-studio-params-v1","source":mode,"values":self._detail_snapshot(mode)}
        self._parameter_clipboard=payload
        try:self.clipboard_clear(); self.clipboard_append(json.dumps(payload,ensure_ascii=False)); self.update_idletasks()
        except tk.TclError:pass
        self.set_status("参数已复制，可切换模式后粘贴")

    def _paste_detail(self,mode):
        payload=self._parameter_clipboard
        try:
            external=json.loads(self.clipboard_get())
            if external.get("format")=="launchpad-studio-params-v1":payload=external
        except Exception:pass
        if not payload:return self.set_status("剪贴板中没有可用的参数")
        self._apply_detail_snapshot(mode,payload.get("values",{}))
        self.set_status(f"已粘贴对应参数（来源：{payload.get('source','未知')}）")

    def _page_live(self):
        self._page_title("实时拾音","从麦克风或系统回放设备低延迟生成灯光。系统声音请选择“立体声混音 / Stereo Mix / Loopback”。")
        self._macro_control_switch()
        saved=self.settings_store.data["detail_params"]["live"]
        tk.Label(self.page,text="音频输入",bg=BG,fg=MUTED).pack(anchor="w",pady=(4,4))
        self.live_devices=audio_devices(); self.live_device=tk.StringVar()
        self.live_combo=ttk.Combobox(self.page,textvariable=self.live_device,state="readonly",values=[n for _,n in self.live_devices]); self.live_combo.pack(fill="x")
        if self.live_devices:
            saved_device=self.settings_store.data.get("live_device","")
            self.live_combo.current(next((i for i,(_,name) in enumerate(self.live_devices) if name==saved_device),0))
        self.live_combo.bind("<<ComboboxSelected>>",lambda _e:self._live_device_changed())
        ttk.Button(self.page,text="刷新输入设备",command=lambda:self._show_mode("实时拾音")).pack(fill="x",pady=(6,14))
        tk.Label(self.page,text="实时风格",bg=BG,fg=MUTED).pack(anchor="w",pady=(4,4))
        self.live_style=tk.StringVar(value=saved.get("style","星云")); style=ttk.Combobox(self.page,textvariable=self.live_style,state="readonly",values=self._visual_styles()); style.pack(fill="x"); style.bind("<<ComboboxSelected>>",lambda _e:self._update_live_visual())
        self._build_preset_controls("live")
        self.live_visual_vars=self._build_visual_parameters("live",lambda:self._update_live_visual())
        latency=self._card(); tk.Label(latency,text="目标延迟",bg=PANEL2,fg=MUTED).pack(side="left"); tk.Label(latency,text="≈ 20–45 ms",bg=PANEL2,fg=GOOD).pack(side="right")
        ttk.Button(self.page,text="开始实时灯光",style="Accent.TButton",command=self._start_live).pack(fill="x",pady=(14,6))
        ttk.Button(self.page,text="停止",command=lambda:self._stop_mode("实时拾音",True)).pack(fill="x")

    def _start_live(self):
        if not self.live_devices:return messagebox.showerror("没有输入设备","未发现可用的麦克风或回放输入设备。")
        idx=self.live_combo.current(); device=self.live_devices[max(0,idx)][0]
        try:
            self._activate_mode("实时拾音")
            if not self.live:self.live=LiveAudio(lambda frame:self.submit_frame(frame,"实时拾音"),self.set_status)
            self.live.start(device,self.live_style.get(),self.palette_var.get(),self.brightness.get()/100,self._visual_params(self.live_visual_vars),self._output_size("实时拾音"))
        except Exception as e:messagebox.showerror("拾音启动失败",str(e))

    def _update_live_visual(self):
        if self.live and hasattr(self,"live_visual_vars"):self.live.set_visual(self.live_style.get(),self.palette_var.get(),self.brightness.get()/100,self._visual_params(self.live_visual_vars),self._output_size("实时拾音"))
        self._schedule_param_save("live")

    def _live_device_changed(self):
        self.settings_store.data["live_device"]=self.live_device.get(); self._schedule_settings_save()

    def _page_utilities(self):
        self._page_title("工具与解压游戏","让 Launchpad 在桌面常驻时也有用：时间、天气、专注提醒和可直接按键游玩的小游戏。")
        cfg=self.settings_store.data["utilities"]
        tk.Label(self.page,text="选择功能",bg=BG,fg=MUTED).pack(anchor="w",pady=(2,4))
        choices=["数字时钟","日历","天气","专注计时器","贪吃蛇","打地鼠","瀑布音游","环形音游"]
        self.utility_choice=tk.StringVar(value=cfg.get("selected","数字时钟"))
        combo=ttk.Combobox(self.page,textvariable=self.utility_choice,state="readonly",values=choices); combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>",lambda _e:self._utility_selection_changed())
        self.utility_options=tk.Frame(self.page,bg=BG); self.utility_options.pack(fill="x",pady=(10,0))
        self._build_utility_options()

    def _utility_selection_changed(self):
        self.settings_store.data["utilities"]["selected"]=self.utility_choice.get(); self.settings_store.save()
        self._build_utility_options()

    def _build_utility_options(self):
        for widget in self.utility_options.winfo_children():widget.destroy()
        choice=self.utility_choice.get(); cfg=self.settings_store.data["utilities"]
        if choice not in ("贪吃蛇","打地鼠","瀑布音游","环形音游"):self._macro_control_switch(self.utility_options)
        if choice in ("数字时钟","日历"):
            text="滚动显示当前 24 小时时间，并用顶排显示秒钟位置。" if choice=="数字时钟" else "滚动显示月-日，顶排亮点表示星期进度。"
            tk.Label(self.utility_options,text=text,bg=BG,fg=MUTED,wraplength=300,justify="left").pack(anchor="w",pady=5)
            self.utility_info=tk.Label(self.utility_options,text="--",bg=PANEL2,fg=TEXT,font=("Segoe UI Semibold",18),padx=12,pady=12); self.utility_info.pack(fill="x",pady=6)
        elif choice=="天气":
            tk.Label(self.utility_options,text="城市名称",bg=BG,fg=MUTED).pack(anchor="w")
            self.weather_city=tk.StringVar(value=cfg.get("weather_city","北京")); ttk.Entry(self.utility_options,textvariable=self.weather_city).pack(fill="x",pady=(3,6))
            self.utility_info=tk.Label(self.utility_options,text="点击开始以获取天气",bg=PANEL2,fg=TEXT,font=("Segoe UI",10),padx=12,pady=12,justify="left"); self.utility_info.pack(fill="x",pady=6)
        elif choice=="专注计时器":
            row=tk.Frame(self.utility_options,bg=BG); row.pack(fill="x")
            tk.Label(row,text="专注分钟数",bg=BG,fg=MUTED).pack(side="left")
            self.focus_minutes=tk.IntVar(value=cfg.get("focus_minutes",25)); ttk.Spinbox(row,from_=1,to=180,textvariable=self.focus_minutes,width=8).pack(side="right")
            self.utility_info=tk.Label(self.utility_options,text=f"{self.focus_minutes.get():02d}:00",bg=PANEL2,fg=TEXT,font=("Segoe UI Semibold",20),padx=12,pady=12); self.utility_info.pack(fill="x",pady=8)
            buttons=tk.Frame(self.utility_options,bg=BG); buttons.pack(fill="x")
            ttk.Button(buttons,text="暂停/继续",command=self._pause_focus).pack(side="left",expand=True,fill="x")
            ttk.Button(buttons,text="重置",command=self._reset_focus).pack(side="left",expand=True,fill="x",padx=(5,0))
        elif choice in ("瀑布音游","环形音游"):
            explanation=("音符从顶部落向底部琴键，到达亮线时按对应底排键。" if choice=="瀑布音游" else
                         "音符从中心向外圈移动，到达外圈目标时按对应键，玩法灵感来自环形街机音游。")
            tk.Label(self.utility_options,text=explanation,bg=BG,fg=MUTED,wraplength=300,justify="left").pack(anchor="w",pady=5)
            path=cfg.get("rhythm_path",""); self.rhythm_file_label=tk.Label(self.utility_options,text=Path(path).name if path else "尚未导入音乐",
                bg=PANEL2,fg=TEXT,font=("Segoe UI",9),padx=10,pady=8,anchor="w"); self.rhythm_file_label.pack(fill="x",pady=4)
            ttk.Button(self.utility_options,text="导入音乐并自动生成谱面",command=self._choose_rhythm_audio).pack(fill="x",pady=(2,8))
            params=tk.Frame(self.utility_options,bg=BG); params.pack(fill="x")
            self.rhythm_difficulty=tk.StringVar(value=cfg.get("rhythm_difficulty","普通"))
            self.rhythm_speed=tk.IntVar(value=cfg.get("rhythm_speed",3)); self.rhythm_lanes=tk.IntVar(value=cfg.get("rhythm_lanes",6))
            for column,(label,var,values) in enumerate((("难度",self.rhythm_difficulty,("简单","普通","困难")),
                                                       ("下落速度",self.rhythm_speed,(1,2,3,4,5)),
                                                       ("琴键数量",self.rhythm_lanes,(4,5,6,7,8)))):
                box=tk.Frame(params,bg=BG); box.grid(row=0,column=column,sticky="ew",padx=(0 if column==0 else 3,0))
                tk.Label(box,text=label,bg=BG,fg=MUTED,font=("Segoe UI",8)).pack(anchor="w")
                combo=ttk.Combobox(box,textvariable=var,state="readonly",values=values,width=7); combo.pack(fill="x")
                combo.bind("<<ComboboxSelected>>",lambda _e,regen=label!="下落速度":self._rhythm_parameters_changed(regen))
                params.grid_columnconfigure(column,weight=1)
            self.utility_info=tk.Label(self.utility_options,text="导入音乐后将自动分析节拍并生成谱面",bg=PANEL2,fg=TEXT,font=("Segoe UI Semibold",11),padx=10,pady=10,wraplength=280,justify="left")
            self.utility_info.pack(fill="x",pady=8)
            controls=tk.Frame(self.utility_options,bg=BG); controls.pack(fill="x")
            ttk.Button(controls,text="重新生成谱面",command=self._regenerate_rhythm_chart).pack(side="left",expand=True,fill="x")
            self.rhythm_pause_btn=ttk.Button(controls,text="暂停 / 继续",command=self._pause_rhythm)
            self.rhythm_pause_btn.pack(side="left",expand=True,fill="x",padx=(5,0))
            if path and self.rhythm_chart_key!=self._rhythm_key():self.after(50,self._regenerate_rhythm_chart)
        else:
            instructions="键盘方向键控制；Launchpad 顶排前四键按实机图标依次为 ↑、↓、←、→。到达边缘会从另一侧出现。" if choice=="贪吃蛇" else "在亮起的方块熄灭前按下它。命中后会重新获得完整反应时间。"
            tk.Label(self.utility_options,text=instructions,bg=BG,fg=MUTED,wraplength=300,justify="left").pack(anchor="w",pady=5)
            game_key="snake" if choice=="贪吃蛇" else "mole"
            difficulty_row=tk.Frame(self.utility_options,bg=BG); difficulty_row.pack(fill="x",pady=(3,5))
            tk.Label(difficulty_row,text="难度",bg=BG,fg=MUTED).pack(side="left")
            self.game_difficulty=tk.StringVar(value=cfg.get(f"{game_key}_difficulty","简单"))
            difficulty=ttk.Combobox(difficulty_row,textvariable=self.game_difficulty,state="readonly",values=("简单","普通","困难"),width=9)
            difficulty.pack(side="right"); difficulty.bind("<<ComboboxSelected>>",lambda _e:self._game_difficulty_changed())
            self.utility_info=tk.Label(self.utility_options,text="得分 0",bg=PANEL2,fg=TEXT,font=("Segoe UI Semibold",16),padx=12,pady=10); self.utility_info.pack(fill="x",pady=6)
        ttk.Button(self.utility_options,text="开始 / 重新开始",style="Accent.TButton",command=self._start_utility).pack(fill="x",pady=(10,5))
        ttk.Button(self.utility_options,text="停止并熄灯",command=lambda:self._stop_utility(True)).pack(fill="x")

    def _rhythm_key(self):
        cfg=self.settings_store.data["utilities"]
        path=cfg.get("rhythm_path",""); style=self.utility_choice.get() if hasattr(self,"utility_choice") else "瀑布音游"
        difficulty=self.rhythm_difficulty.get() if hasattr(self,"rhythm_difficulty") else cfg.get("rhythm_difficulty","普通")
        lanes=int(self.rhythm_lanes.get()) if hasattr(self,"rhythm_lanes") else int(cfg.get("rhythm_lanes",6))
        return path,style,difficulty,lanes

    def _choose_rhythm_audio(self):
        paths=self._pick_files("导入音游音乐","音频文件|*.wav;*.mp3;*.ogg;*.flac;*.aiff|所有文件|*.*")
        if not paths:return
        self.settings_store.data["utilities"]["rhythm_path"]=paths[0]; self.settings_store.save()
        self.rhythm_file_label.configure(text=Path(paths[0]).name); self._regenerate_rhythm_chart()

    def _rhythm_parameters_changed(self,regenerate=True):
        cfg=self.settings_store.data["utilities"]
        cfg["rhythm_difficulty"]=self.rhythm_difficulty.get(); cfg["rhythm_speed"]=int(self.rhythm_speed.get()); cfg["rhythm_lanes"]=int(self.rhythm_lanes.get())
        self.settings_store.save()
        if regenerate:self._regenerate_rhythm_chart()
        else:self.set_status("音符下落速度已保存；下次开始时生效")

    def _regenerate_rhythm_chart(self):
        if self.rhythm_generating:return
        key=self._rhythm_key(); path=key[0]
        if not path or not Path(path).exists():return self._set_utility_info("请先导入可读取的音乐文件",key[1])
        self.rhythm_generating=True; self.rhythm_chart=None; self.rhythm_chart_key=None
        self._set_utility_info("正在识别节拍、瞬态和频段并生成谱面…",key[1]); self.set_status("正在生成音游谱面")
        def work():
            try:
                chart,analysis=generate_chart(*key); self._queue_ui(("rhythm_chart",key,chart,analysis))
            except Exception as exc:self._queue_ui(("rhythm_error",key,str(exc)))
        threading.Thread(target=work,daemon=True,name="RhythmChartGenerator").start()

    def _rhythm_chart_ready(self,key,chart,analysis):
        self.rhythm_generating=False
        self.rhythm_chart_key=key; self.rhythm_chart=chart; self.rhythm_analysis=analysis
        if self.mode=="工具与游戏" and self.utility_choice.get() in ("瀑布音游","环形音游"):
            if key!=self._rhythm_key():return self._regenerate_rhythm_chart()
            self._set_utility_info(f"谱面已生成 · BPM {chart.bpm} · {len(chart.notes)} 个音符 · {chart.lanes} 键\n点击开始进入游戏",chart.style)
            self.set_status("音游谱面生成完成")

    def _rhythm_chart_failed(self,key,error):
        self.rhythm_generating=False
        if self.mode=="工具与游戏" and self.utility_choice.get()==key[1]:self._set_utility_info(f"谱面生成失败：{error}",key[1])
        self.set_status(f"谱面生成失败：{error}")

    def _utility_colors(self):
        low,high=PALETTES.get(self.palette_var.get(),PALETTES["霓虹"])
        amount=self.brightness.get()/100
        return tuple(round(v*amount) for v in low),tuple(round(v*amount) for v in high)

    def _game_difficulty_changed(self):
        choice=self.utility_choice.get()
        if choice not in ("贪吃蛇","打地鼠"):return
        key="snake_difficulty" if choice=="贪吃蛇" else "mole_difficulty"
        self.settings_store.data["utilities"][key]=self.game_difficulty.get(); self.settings_store.save()
        self.set_status("难度已保存；点击开始后生效")

    def _game_delay(self,choice):
        key="snake_difficulty" if choice=="贪吃蛇" else "mole_difficulty"
        difficulty=self.settings_store.data["utilities"].get(key,"简单")
        if choice=="贪吃蛇":
            base={"简单":520,"普通":340,"困难":230}.get(difficulty,520)
            floor={"简单":220,"普通":140,"困难":95}.get(difficulty,220)
            return max(floor,base-(self.snake.level-1)*28)
        base={"简单":1600,"普通":1100,"困难":750}.get(difficulty,1600)
        floor={"简单":720,"普通":480,"困难":320}.get(difficulty,720)
        return max(floor,base-(self.mole.level-1)*80)

    def _update_game_scoreboard(self,choice):
        cfg=self.settings_store.data["utilities"]
        if choice=="贪吃蛇":
            high=max(cfg.get("snake_high_score",0),self.snake.score)
            self._set_utility_info(f"得分 {self.snake.score} · 第 {self.snake.level} 关\n最高 {high}",choice)
            return high
        high=max(cfg.get("mole_high_score",0),self.mole.score)
        remaining=max(0,self.mole.max_misses-self.mole.misses)
        self._set_utility_info(f"得分 {self.mole.score} · 第 {self.mole.level} 关\n剩余机会 {remaining}/{self.mole.max_misses} · 最高 {high}",choice)
        return high

    def _set_utility_info(self,text,choice=None):
        visible=(self.mode=="工具与游戏" and hasattr(self,"utility_info") and
                 (choice is None or self.utility_choice.get()==choice))
        if visible:
            try:self.utility_info.configure(text=text)
            except tk.TclError:pass

    def _play_score_effect(self,base_frame,score):
        self.score_effect_token+=1; token=self.score_effect_token; self.score_effect_until=time.monotonic()+.225
        low,high=self._utility_colors(); width,height=self._output_size("工具与游戏")
        for phase,delay in enumerate((0,75,150)):
            frame=dict(base_frame)
            color=high if phase%2==0 else tuple(min(255,v+90) for v in low)
            for x,y in frame:
                if frame.get((x,y),(0,0,0))!=(0,0,0):continue
                if y==0 or x==width or x in (0,width-1) or y in (1,height):
                    if (x+y+phase+score)%3==0:frame[(x,y)]=color
            self.after(delay,lambda f=frame,t=token:self._score_effect_step(t,f))
        self.after(225,lambda f=dict(base_frame),t=token:self._score_effect_step(t,f))

    def _score_effect_step(self,token,frame):
        if token==self.score_effect_token and self.utility_running and "工具与游戏" in self.active_modes:
            self.apply_frame(frame,"工具与游戏")

    def _rhythm_score_overlay(self,frame):
        if time.monotonic()>=self.rhythm_score_effect_until:return frame
        result=dict(frame); low,high=self._utility_colors(); phase=int(time.monotonic()*24)
        width,height=self._output_size("工具与游戏")
        for x in range(width):result[(x,0)]=high if (x+phase)%2 else low
        for y in range(1,height+1):result[(width,y)]=high if (y+phase)%2 else low
        return result

    def _start_utility(self):
        choice=self.utility_choice.get(); cfg=self.settings_store.data["utilities"]
        if choice in ("瀑布音游","环形音游") and (not self.rhythm_chart or self.rhythm_chart_key!=self._rhythm_key()):
            self._set_utility_info("谱面尚未生成完成，请稍候或点击重新生成谱面",choice); return
        self._stop_utility(clear=False); self._activate_mode("工具与游戏")
        self.active_mode="工具与游戏"; self.active_utility=choice; self.utility_running=True; self.utility_phase=0
        if choice=="天气":
            city=self.weather_city.get().strip() or "北京"; cfg["weather_city"]=city; self.settings_store.save()
            self.utility_info.configure(text="正在获取天气…"); self.set_status(f"正在查询 {city} 天气")
            threading.Thread(target=self._weather_worker,args=(city,),daemon=True,name="WeatherFetch").start()
        elif choice=="专注计时器":
            minutes=max(1,min(180,int(self.focus_minutes.get()))); cfg["focus_minutes"]=minutes; self.settings_store.save()
            self.focus_remaining=minutes*60; self.focus_deadline=time.monotonic()+self.focus_remaining; self.focus_paused=False
        elif choice=="贪吃蛇":
            cfg["snake_difficulty"]=self.game_difficulty.get(); self.snake.reset(*self._output_size("工具与游戏")); self.snake_first_tick=True; self.settings_store.save()
        elif choice=="打地鼠":
            difficulty=self.game_difficulty.get(); cfg["mole_difficulty"]=difficulty
            self.mole.reset({"简单":8,"普通":5,"困难":3}.get(difficulty,8),*self._output_size("工具与游戏")); self.mole_first_tick=True; self.settings_store.save()
        elif choice in ("瀑布音游","环形音游"):
            difficulty=self.rhythm_difficulty.get(); speed=int(self.rhythm_speed.get()); lanes=int(self.rhythm_lanes.get())
            cfg.update(rhythm_difficulty=difficulty,rhythm_speed=speed,rhythm_lanes=lanes); self.settings_store.save()
            self.rhythm_game.reset(self.rhythm_chart,speed,difficulty)
            if not self.rhythm_audio:
                self.rhythm_audio=MusicShow(lambda _frame:None,lambda _status:None,lambda _p,_d:None,
                                            lambda:self._queue_ui(("rhythm_finished",)),emit_frames=False)
            self.rhythm_audio.analysis=self.rhythm_analysis; self.rhythm_audio.path=self.rhythm_chart.path
            self.rhythm_audio.start(self.rhythm_chart.path,"频谱",self.palette_var.get(),0,{})
        self.set_status(f"{choice}运行中"); self._utility_tick()

    def _weather_worker(self,city):
        try:self._queue_ui(("weather_result",self.weather.fetch(city)))
        except Exception as exc:self._queue_ui(("weather_error",str(exc)))

    def _weather_ready(self,data):
        self.weather_data=data
        if self.mode=="工具与游戏" and hasattr(self,"utility_choice") and self.utility_choice.get()=="天气":
            self.utility_info.configure(text=(f"{data['place']}\n{data['description']}  {data['temperature']:.1f} °C（体感 {data['apparent']:.1f} °C）\n"
                                              f"最高 {data['high']:.1f}°  最低 {data['low']:.1f}°  降水 {data['rain']}%\n"
                                              f"湿度 {data['humidity']}%  风速 {data['wind']:.1f} km/h"))
            self.set_status("天气已更新")

    def _utility_tick(self):
        if not self.utility_running or "工具与游戏" not in self.active_modes:return
        choice=self.active_utility; low,high=self._utility_colors(); output_size=self._output_size("工具与游戏"); now=datetime.now(); delay=500; scored=False
        if choice=="数字时钟":
            self._set_utility_info(now.strftime("%H:%M:%S"),choice); frame=clock_frame(now,self.utility_phase,low,high,output_size); delay=500
        elif choice=="日历":
            weekdays="一二三四五六日"; self._set_utility_info(f"{now:%Y年%m月%d日} · 星期{weekdays[now.weekday()]}",choice)
            frame=calendar_frame(now,self.utility_phase,low,high,output_size); delay=700
        elif choice=="天气":
            frame=weather_frame(self.weather_data["code"],self.weather_data["temperature"],low,high,output_size) if self.weather_data else scrolling_text("----",self.utility_phase,low,high,output_size); delay=700
        elif choice=="专注计时器":
            if not self.focus_paused and self.focus_deadline:self.focus_remaining=max(0,int(self.focus_deadline-time.monotonic()+.999))
            minutes,seconds=divmod(self.focus_remaining,60); value=f"{minutes:02d}:{seconds:02d}"
            self._set_utility_info(value,choice); frame=scrolling_text(value,self.utility_phase,low,high,output_size); delay=500
            if self.focus_remaining<=0:
                self.utility_running=False; self.set_status("专注计时完成")
                try:self.tray_icon.notify("休息一下吧，专注计时已经完成。","Launchpad Studio")
                except Exception:pass
        elif choice=="贪吃蛇":
            alive=True; previous_score=self.snake.score
            if not getattr(self,"snake_first_tick",False):alive=self.snake.tick()
            scored=self.snake.score>previous_score
            self.snake_first_tick=False; frame=self.snake.frame(); high_score=self._update_game_scoreboard(choice); delay=self._game_delay(choice)
            if not alive:
                self.settings_store.data["utilities"]["snake_high_score"]=high_score; self.settings_store.save(); self.utility_running=False; self.set_status("贪吃蛇游戏结束")
        elif choice=="打地鼠":
            if not getattr(self,"mole_first_tick",False):self.mole.timeout()
            self.mole_first_tick=False; frame=self.mole.frame(); high_score=self._update_game_scoreboard(choice); delay=self._game_delay(choice)
            if not self.mole.running:
                self.settings_store.data["utilities"]["mole_high_score"]=high_score; self.settings_store.save(); self.utility_running=False; self.set_status("打地鼠游戏结束")
        else:
            position=self._rhythm_position(); self.rhythm_game.update(position)
            frame=self._rhythm_score_overlay(self.rhythm_game.frame(position,low,high,output_size=output_size)); self._update_rhythm_scoreboard(choice); delay=33
            if not self.rhythm_game.running:self._finish_rhythm_game(choice,frame)
        if time.monotonic()>=self.score_effect_until:self.apply_frame(frame,"工具与游戏")
        self.utility_phase+=1
        if scored:self._play_score_effect(frame,self.snake.score); delay=max(delay,260)
        if self.utility_running:self.utility_job=self.after(delay,self._utility_tick)

    def _pause_focus(self):
        if self.active_utility!="专注计时器" or not self.utility_running:return
        if self.focus_paused:
            self.focus_deadline=time.monotonic()+self.focus_remaining; self.focus_paused=False; self.set_status("专注计时继续")
        else:
            self.focus_remaining=max(0,int(self.focus_deadline-time.monotonic()+.999)); self.focus_paused=True; self.set_status("专注计时已暂停")

    def _reset_focus(self):
        if "工具与游戏" in self.active_modes and self.active_utility=="专注计时器":self._stop_utility(clear=True)
        self.focus_remaining=max(1,int(self.focus_minutes.get()))*60
        if hasattr(self,"utility_info"):self.utility_info.configure(text=f"{self.focus_remaining//60:02d}:00")

    def _rhythm_position(self):
        if not self.rhythm_audio or not self.rhythm_audio.analysis:return 0.0
        with self.rhythm_audio.lock:return self.rhythm_audio.cursor/self.rhythm_audio.analysis.sr

    def _update_rhythm_scoreboard(self,choice):
        key="waterfall_high_score" if choice=="瀑布音游" else "maimai_high_score"
        high=max(self.settings_store.data["utilities"].get(key,0),self.rhythm_game.score)
        total=max(1,self.rhythm_game.hits+self.rhythm_game.misses); accuracy=self.rhythm_game.hits/total*100
        self._set_utility_info(f"得分 {self.rhythm_game.score} · 连击 {self.rhythm_game.combo}（最高 {self.rhythm_game.max_combo}）\n"
                               f"命中 {self.rhythm_game.hits} · 失误 {self.rhythm_game.misses} · 准确率 {accuracy:.1f}% · 最高分 {high}",choice)
        return key,high

    def _pause_rhythm(self):
        if self.active_utility not in ("瀑布音游","环形音游") or not self.utility_running or not self.rhythm_audio:return
        paused=self.rhythm_audio.pause_toggle(); self.set_status("音游已暂停" if paused else "音游继续")
        if hasattr(self,"rhythm_pause_btn"):
            try:self.rhythm_pause_btn.configure(text="继续" if paused else "暂停")
            except tk.TclError:pass

    def _finish_rhythm_game(self,choice=None,frame=None):
        choice=choice or self.active_utility
        if choice not in ("瀑布音游","环形音游"):return
        self.rhythm_game.running=False; key,high=self._update_rhythm_scoreboard(choice)
        self.settings_store.data["utilities"][key]=high; self.settings_store.save(); self.utility_running=False
        if frame is None:
            low,high_color=self._utility_colors(); frame=self.rhythm_game.frame(self._rhythm_position(),low,high_color,output_size=self._output_size("工具与游戏"))
        self.apply_frame(frame,"工具与游戏")
        if self.rhythm_audio:self.rhythm_audio.stop()
        self.set_status(f"{choice}结束 · 得分 {self.rhythm_game.score}")

    def _stop_utility(self,clear=False):
        was_active="工具与游戏" in self.active_modes
        self.utility_running=False
        if self.utility_job:
            try:self.after_cancel(self.utility_job)
            except Exception:pass
            self.utility_job=None
        if self.rhythm_audio:self.rhythm_audio.stop()
        self.active_utility=None; self.score_effect_token+=1
        if was_active:
            self.active_modes.discard("工具与游戏"); self.mode_frames.pop("工具与游戏",None)
            if self.active_mode=="工具与游戏":self.active_mode=next(iter(self.active_modes),None)
            if clear:self.apply_frame(blank(self._output_size("工具与游戏")),"工具与游戏"); self.mode_frames.pop("工具与游戏",None); self.set_status("工具/游戏已停止")

    def _utility_key(self,event):
        if "工具与游戏" not in self.active_modes or not self.utility_running or self.active_utility!="贪吃蛇":return
        direction={"Left":(-1,0),"Up":(0,-1),"Down":(0,1),"Right":(1,0)}.get(event.keysym)
        if direction:self.snake.steer(direction)

    def _utility_pad(self,x,y,device_id=None):
        if not self.utility_running:return
        if (self.multi_cfg.get("enabled") and self.multi_cfg.get("link_mode")==LINK_EXTEND and
                device_id is not None and 0<=x<8 and 1<=y<=8):
            _,_,positions=canvas_geometry(self._layout_configs()); tile=positions.get(str(device_id))
            if tile:x,y=tile[0]*8+x,tile[1]*8+y
        choice=self.active_utility
        if choice=="贪吃蛇":
            directions={0:(0,-1),1:(0,1),2:(-1,0),3:(1,0)}
            if y==0 and x in directions:self.snake.steer(directions[x])
            elif 0<=x<self.snake.width and 1<=y<=self.snake.height:
                hx,hy=self.snake.snake[0]; dx,dy=x-hx,y-hy
                self.snake.steer((1 if dx>0 else -1,0) if abs(dx)>abs(dy) else (0,1 if dy>0 else -1))
        elif choice=="打地鼠" and 0<=x<self.mole.width and 1<=y<=self.mole.height:
            hit=self.mole.hit((x,y)); self.set_status("命中！" if hit else "没有打中")
            high_score=self._update_game_scoreboard(choice); self.apply_frame(self.mole.frame(),"工具与游戏")
            if hit:self._play_score_effect(self.mole.frame(),self.mole.score)
            if not self.mole.running:
                if self.utility_job:
                    try:self.after_cancel(self.utility_job)
                    except Exception:pass
                    self.utility_job=None
                self.settings_store.data["utilities"]["mole_high_score"]=high_score; self.settings_store.save(); self.utility_running=False; self.set_status("打地鼠游戏结束")
            elif hit:
                # A successful hit starts a full fresh reaction window for the
                # new target instead of inheriting the previous timer.
                if self.utility_job:
                    try:self.after_cancel(self.utility_job)
                    except Exception:pass
                self.utility_job=self.after(self._game_delay(choice),self._utility_tick)
        elif choice in ("瀑布音游","环形音游"):
            output_size=self._output_size("工具与游戏")
            result=self.rhythm_game.hit((x,y),self._rhythm_position(),output_size)
            low,high=self._utility_colors(); frame=self.rhythm_game.frame(self._rhythm_position(),low,high,output_size=output_size)
            if result and result!="miss":self.rhythm_score_effect_until=time.monotonic()+.25
            self.apply_frame(self._rhythm_score_overlay(frame),"工具与游戏"); self._update_rhythm_scoreboard(choice)
            self.set_status({"perfect":"PERFECT！","great":"GREAT！","good":"GOOD！","miss":"MISS"}.get(result,"请按亮起的目标琴键"))

    def _canvas_pad(self,x,y,device_id=None):
        if self.mode=="布局设置" and device_id:self._select_layout_device(device_id)
        elif self.mode=="宏按键":self._load_macro_form(x,y)
        elif self.mode=="工具与游戏":self._utility_pad(x,y,device_id)

    def _canvas_layout_move(self,device_id,x,y):
        devices=self.multi_cfg.get("devices",[])
        item=next((row for row in devices if str(row.get("id"))==str(device_id)),None)
        if not item:return
        old_x,old_y=int(item.get("x",0)),int(item.get("y",0))
        other=next((row for row in devices if row is not item and (int(row.get("x",0)),int(row.get("y",0)))==(x,y)),None)
        item.update(x=int(x),y=int(y))
        if other:other.update(x=old_x,y=old_y)
        self.settings_store.save(); self._global_visual_update(); self._redispatch_frames(); self._sync_canvas_preview()
        if self.mode=="布局设置":self._show_mode("布局设置")
        self.set_status(f"LP {item.get('number',1)} 已移动到 ({x}, {y})"+("，并与目标设备交换位置" if other else ""))

    def _hardware_pad(self,x,y,pressed,velocity,device_id="lp1"):
        self.after(0,lambda:self._handle_pad_ui(x,y,pressed,device_id))

    def _handle_pad_ui(self,x,y,pressed,device_id="lp1"):
        if not pressed:return
        self.pad_canvas.select_pad(x,y,device_id)
        games=("贪吃蛇","打地鼠","瀑布音游","环形音游")
        device_mode=self.active_mode
        if self.multi_cfg.get("enabled") and self.multi_cfg.get("link_mode")==LINK_INDEPENDENT:
            device_mode=next((item.get("mode") for item in self._layout_configs() if str(item.get("id"))==str(device_id)),device_mode)
        if device_mode=="工具与游戏" and "工具与游戏" in self.active_modes and self.active_utility in games:
            self._utility_pad(x,y,device_id)
        elif device_mode=="宏按键" or self.mode=="宏按键" or self.settings_store.data.get("macro_control_enabled",False):
            macro=self._macro_get(x,y)
            if macro:self.macro_exec.execute(macro); self.set_status(f"已执行按键 {self.lp.pad_label(x,y)} · {macro['action']}")

    def _palette_changed(self,_e=None):
        self.settings_store.data["theme"]=self.palette_var.get(); self.settings_store.save()
        self._global_visual_update()

    def _brightness_changed(self):
        self.settings_store.data["brightness"]=round(self.brightness.get())
        self._schedule_settings_save(); self._global_visual_update()

    def _schedule_settings_save(self):
        if self._settings_save_job:
            try:self.after_cancel(self._settings_save_job)
            except Exception:pass
        self._settings_save_job=self.after(350,self._finish_settings_save)

    def _finish_settings_save(self):
        self._settings_save_job=None; self.settings_store.save()

    def _global_visual_update(self):
        if "音乐演示" in self.active_modes and hasattr(self,"music_visual_vars"):self._update_music_visual()
        if "实时拾音" in self.active_modes and hasattr(self,"live_visual_vars"):self._update_live_visual()
        if "视频播放" in self.active_modes and hasattr(self,"video_vars"):self._update_video_effect()

    def _pick_global_color(self):
        value=colorchooser.askcolor(self.custom_color,title="整体主色")[1]
        if value:
            self.custom_color=value; self.settings_store.data["custom_color"]=value; h=value.lstrip("#"); rgb=tuple(int(h[i:i+2],16) for i in (0,2,4)); PALETTES["自定义"]=(tuple(int(v*.18) for v in rgb),rgb); self.palette_var.set("自定义"); self._palette_changed()

    def _refresh_midi(self):
        self.midi_inputs,self.midi_outputs=self.lp.devices()
        if self.multi_cfg.get("enabled") and self.multi_cfg.get("devices"):
            if not any(device.connected for device in self.launchpads.values()):
                self._connect_launchpad_configs(self.multi_cfg["devices"],silent=True)
        elif not self.lp.connected:
            ins=[i for i,n in enumerate(self.midi_inputs) if is_launchpad_control_port(n)]
            outs=[i for i,n in enumerate(self.midi_outputs) if is_launchpad_control_port(n)]
            if ins and outs:
                try:self.lp.connect(ins[0],outs[0],"auto"); self._connected_ui()
                except Exception as e:self.set_status(f"自动连接失败：{e}")

    def _auto_connect_launchpads(self):
        self.midi_inputs,self.midi_outputs=self.lp.devices()
        input_indices=[index for index,name in enumerate(self.midi_inputs) if is_launchpad_control_port(name)]
        output_indices=[index for index,name in enumerate(self.midi_outputs) if is_launchpad_control_port(name)]
        count=min(len(input_indices),len(output_indices))
        if not count:
            self.set_status("没有发现 Launchpad，请检查 USB 连接后重试"); return
        existing=list(self.multi_cfg.get("devices",[])); used_ids=set(); reserved_ids={str(item.get("id")) for item in existing}; configs=[]
        for ordinal,(input_index,output_index) in enumerate(zip(input_indices[:count],output_indices[:count]),1):
            input_name,output_name=self.midi_inputs[input_index],self.midi_outputs[output_index]
            saved=next((item for item in existing if item.get("input")==input_name and item.get("output")==output_name and str(item.get("id")) not in used_ids),None)
            if saved is None:saved=next((item for item in existing if int(item.get("number",-1))==ordinal and str(item.get("id")) not in used_ids),None)
            device_id=str(saved.get("id")) if saved else next(f"lp{i}" for i in range(1,100) if f"lp{i}" not in used_ids and f"lp{i}" not in reserved_ids)
            used_ids.add(device_id)
            configs.append({"id":device_id,"number":ordinal,"x":int(saved.get("x",ordinal-1)) if saved else ordinal-1,
                            "y":int(saved.get("y",0)) if saved else 0,"mode":saved.get("mode","性能监控") if saved else "性能监控",
                            "model":saved.get("model","auto") if saved else "auto","input":input_name,"output":output_name,
                            "input_index":input_index,"output_index":output_index})
        self.multi_cfg.update(enabled=count>1,devices=configs)
        self.settings_store.data["launchpad_model"]=configs[0]["model"]; self.settings_store.save()
        complete=self._connect_launchpad_configs(configs if count>1 else configs[:1],silent=True)
        self._global_visual_update(); self._redispatch_frames(); self._show_mode("布局设置")
        if len(input_indices)!=len(output_indices):self.set_status(f"已连接 {count} 台；另有 MIDI 输入/输出未成对")
        else:self.set_status(f"已自动识别并连接 {count} 台 Launchpad" if complete else f"已识别 {count} 台，部分设备连接失败")

    @staticmethod
    def _port_label(index,names):
        return f"{index} · {names[index]}" if 0<=index<len(names) else ""

    @staticmethod
    def _port_index(item,key,names,used):
        index=int(item.get(f"{key}_index",-1))
        saved=str(item.get(key,""))
        if 0<=index<len(names) and index not in used and (not saved or names[index]==saved):return index
        return next((i for i,name in enumerate(names) if i not in used and name==saved),-1)

    def _connect_launchpad_configs(self,configs,silent=False):
        for device in {id(device):device for device in self.launchpads.values()}.values():device.disconnect(clear=False)
        connected={}; errors=[]; used_inputs=set(); used_outputs=set()
        for index,item in enumerate(sorted(configs,key=lambda row:int(row.get("number",99)))):
            device_id=str(item.get("id") or f"lp{index+1}")
            in_index=self._port_index(item,"input",self.midi_inputs,used_inputs)
            out_index=self._port_index(item,"output",self.midi_outputs,used_outputs)
            if in_index<0 or out_index<0:
                errors.append(f"LP{item.get('number',index+1)}：MIDI 端口不存在"); continue
            device=self.lp if not connected else LaunchpadDevice()
            device.on_press=lambda x,y,pressed,velocity,did=device_id:self._hardware_pad(x,y,pressed,velocity,did)
            try:
                device.connect(in_index,out_index,str(item.get("model","auto")))
                item.update(id=device_id,input=self.midi_inputs[in_index],output=self.midi_outputs[out_index],
                            input_index=in_index,output_index=out_index)
                connected[device_id]=device; used_inputs.add(in_index); used_outputs.add(out_index)
            except Exception as exc:errors.append(f"LP{item.get('number',index+1)}：{exc}")
        if connected:
            self.launchpads=connected; self.lp=next(iter(connected.values()))
            if hasattr(self,"pad_canvas"):self.pad_canvas.launchpad=self.lp
            self._connected_ui()
        else:self.launchpads={"lp1":self.lp}
        if errors and not silent:messagebox.showwarning("部分设备未连接","\n".join(errors),parent=self)
        return not errors

    def _midi_watchdog(self):
        if self._closing:return
        if not any(device.connected for device in self.launchpads.values()):
            try:self._refresh_midi()
            except Exception:logging.debug("MIDI reconnect check failed",exc_info=True)
        self.after(3000,self._midi_watchdog)

    def _device_dialog(self):
        self._show_mode("布局设置")


    def _connected_ui(self):
        model=self.lp.model
        count=sum(device.connected for device in self.launchpads.values())
        self.status_dot.configure(fg=GOOD); self.device_status.configure(text=f"{count} 台 Launchpad 已连接" if count>1 else f"{model.name} 已连接",fg=GOOD)
        self.model_footer.configure(text=f"{model.name} · {len(model.pads)} LEDs")
        self.pad_canvas.colors={xy:(0,0,0) for xy in model.pads}; self.pad_canvas.selected=None; self.pad_canvas.selected_device=None
        self._sync_canvas_preview({key:device.colors for key,device in self.launchpads.items()})
        self.set_status(f"已连接 {count} 台 Launchpad · {self.multi_cfg.get('link_mode',LINK_EXTEND)}" if count>1 else f"真机已连接 · {len(model.pads)} LEDs · {model.name}")

    def _test_lights(self):
        devices=[device for device in self.launchpads.values() if device.connected]
        if not devices:return self._show_mode("布局设置")
        for device in devices:device.test_pattern()
        self._sync_canvas_preview({key:device.colors for key,device in self.launchpads.items()})
        self.set_status(f"{len(devices)} 台 Launchpad RGB 全键灯光测试")

    def _layout_configs(self):
        if self.multi_cfg.get("enabled") and self.multi_cfg.get("devices"):
            connected_ids={key for key,device in self.launchpads.items() if device.connected}
            connected=[item for item in self.multi_cfg["devices"] if str(item.get("id")) in connected_ids]
            return connected or self.multi_cfg["devices"]
        device_id=next((key for key,value in self.launchpads.items() if value is self.lp),"lp1")
        return [{"id":device_id,"number":1,"x":0,"y":0,"mode":self.active_mode or self.mode}]

    def _sync_canvas_preview(self,frames=None):
        if not hasattr(self,"pad_canvas"):return
        configs=[dict(item) for item in self._layout_configs()]
        if self.multi_cfg.get("link_mode",LINK_EXTEND)!=LINK_INDEPENDENT:
            display_mode=self.active_mode or (next(reversed(self.mode_frames)) if self.mode_frames else "待机")
            for item in configs:item["mode"]=display_mode
        full=bool(self.multi_cfg.get("enabled") and len(configs)>1)
        actual={key:device.colors for key,device in self.launchpads.items()}
        if frames is not None:actual.update(frames)
        frames=actual
        self.pad_canvas.launchpad=self.lp
        self.pad_canvas.set_layout(configs,self.launchpads,full)
        self.pad_canvas.set_device_frames(frames)
        if not full:
            primary_id=next((key for key,value in self.launchpads.items() if value is self.lp),None)
            self.pad_canvas.set_frame(frames.get(primary_id,self.current_frame))

    def _output_size(self,_source=None):
        configs=self._layout_configs()
        if self.multi_cfg.get("enabled") and self.multi_cfg.get("link_mode")==LINK_EXTEND:
            width,height,_=canvas_geometry(configs); return width*8,height*8
        return 8,8

    def _redispatch_frames(self):
        if not self.mode_frames:
            for device in self.launchpads.values():
                if device.connected:device.clear(force=True)
            self._sync_canvas_preview({key:device.colors for key,device in self.launchpads.items()})
            return
        source=self.active_mode or next(reversed(self.mode_frames))
        self.apply_frame(self.mode_frames[source],source)

    def submit_frame(self,frame,source=None):
        source=source or self.active_mode or self.mode
        if threading.current_thread() is threading.main_thread():self.apply_frame(frame,source)
        else:self._queue_ui(("frame",source,frame))

    def apply_frame(self,frame,source=None):
        source=source or self.active_mode or self.mode; self.mode_frames[source]=dict(frame)
        configs=self._layout_configs(); pads={key:device.pads for key,device in self.launchpads.items() if device.connected}
        link_mode=self.multi_cfg.get("link_mode",LINK_EXTEND) if self.multi_cfg.get("enabled") else LINK_MIRROR
        routed=route_frames(configs,pads,self.mode_frames,link_mode,source)
        primary_id=next((key for key,value in self.launchpads.items() if value is self.lp),None)
        if primary_id in routed:
            self.current_frame=routed[primary_id]
        self._sync_canvas_preview(routed)
        for device_id,adapted in routed.items():
            try:self.launchpads[device_id].set_frame(adapted)
            except Exception as exc:
                logging.error("MIDI output failed for %s",device_id,exc_info=True)
                self.launchpads[device_id].disconnect(clear=False); self.status_dot.configure(fg=BAD)
                self.set_status(f"{device_id} MIDI 输出错误：{exc}；将自动重连")

    def set_status(self,text):
        if threading.current_thread() is threading.main_thread():self.status_var.set(text)
        else:self._queue_ui(("status",text))

    def _queue_ui(self,event):
        if self._closing:return
        try:self.ui_events.put_nowait(event)
        except queue.Full:
            try:self.ui_events.get_nowait()
            except queue.Empty:pass
            try:self.ui_events.put_nowait(event)
            except queue.Full:pass

    def _drain_ui_events(self):
        latest_frames={}; latest_video=None; latest_audio=None; latest_weather=None; weather_error=None
        try:
            for _ in range(30):
                event=self.ui_events.get_nowait(); kind=event[0]
                if kind=="frame":latest_frames[event[1]]=event[2]
                elif kind=="status":self.status_var.set(event[1])
                elif kind=="video_progress":latest_video=event[1:]
                elif kind=="audio_progress":latest_audio=event[1:]
                elif kind=="video_finished" and "视频播放" in self.active_modes:self._advance_video(1,True)
                elif kind=="audio_finished" and "音乐演示" in self.active_modes:self._advance_audio(1,True)
                elif kind=="weather_result":latest_weather=event[1]
                elif kind=="weather_error":weather_error=event[1]
                elif kind=="rhythm_chart":self._rhythm_chart_ready(*event[1:])
                elif kind=="rhythm_error":self._rhythm_chart_failed(*event[1:])
                elif kind=="rhythm_finished" and "工具与游戏" in self.active_modes:self._finish_rhythm_game()
                elif kind=="remote_command":self._handle_remote_command(event[1],event[2])
                elif kind=="show_window":self._show_window()
                elif kind=="quit_app":self._close()
        except queue.Empty:pass
        for source,frame in latest_frames.items():self.apply_frame(frame,source)
        if latest_video is not None:
            pos,duration=latest_video; self.video_duration=duration
            if self.mode=="视频播放" and hasattr(self,"video_progress"):
                if not self.video_seeking:self.video_progress.set(0 if not duration else pos/duration*1000)
                self.video_time.configure(text=f"{self._fmt_time(pos)} / {self._fmt_time(duration)}")
        if latest_audio is not None:
            pos,duration=latest_audio; self.audio_duration=duration
            if self.mode=="音乐演示" and hasattr(self,"audio_progress"):
                if not self.audio_seeking:self.audio_progress.set(0 if not duration else pos/duration*1000)
                self.audio_time.configure(text=f"{self._fmt_time(pos)} / {self._fmt_time(duration)}")
        if latest_weather is not None:self._weather_ready(latest_weather)
        if weather_error is not None:
            self.set_status(f"天气获取失败：{weather_error}")
            if self.mode=="工具与游戏" and hasattr(self,"utility_info"):self.utility_info.configure(text=f"天气获取失败\n{weather_error}")
        if not self._closing:self.after(16,self._drain_ui_events)

    def _activate_mode(self,name):
        independent=(self.multi_cfg.get("enabled") and self.multi_cfg.get("link_mode")==LINK_INDEPENDENT and len(self._layout_configs())>1)
        if independent:self._stop_mode(name,False,False)
        else:self._stop_all(False)
        self.score_effect_token+=1; self.active_mode=name; self.active_modes.add(name)

    def _stop_mode(self,name,clear=False,set_status=True):
        if name=="性能监控":self.running_perf=False
        elif name=="视频播放":self.video.stop()
        elif name=="音乐演示" and self.music:self.music.stop()
        elif name=="实时拾音" and self.live:self.live.stop()
        elif name=="工具与游戏":self._stop_utility(clear=False)
        self.active_modes.discard(name); self.mode_frames.pop(name,None)
        if self.active_mode==name:self.active_mode=next(iter(self.active_modes),None)
        if clear:
            blank={xy:(0,0,0) for xy in ALL_PADS}; self.mode_frames[name]=blank; self.apply_frame(blank,name); self.mode_frames.pop(name,None)
        if set_status:self.set_status(f"{name}已停止")

    def _stop_all(self,set_status=True):
        self.running_perf=False; self.video.stop()
        if self.music:self.music.stop()
        if self.live:self.live.stop()
        self._stop_utility(clear=False)
        self.active_mode=None; self.active_modes.clear(); self.mode_frames.clear(); self.score_effect_token+=1
        if set_status:self.set_status("已停止")

    def _stop_all_and_clear(self):
        self._stop_all(False)
        for device in self.launchpads.values():device.clear(force=True)
        blank={xy:(0,0,0) for xy in self.lp.pads}; self.current_frame=blank
        self._sync_canvas_preview({key:device.colors for key,device in self.launchpads.items()})
        self.set_status("所有灯光功能已结束，全部 Launchpad 已熄灯")

    def _tray_image(self):
        image=Image.new("RGBA",(64,64),(11,13,18,255)); draw=ImageDraw.Draw(image)
        colors=[(124,92,255,255),(0,225,255,255),(255,45,180,255)]
        for y in range(4):
            for x in range(4):
                c=colors[(x+y)%len(colors)]; x1=7+x*13; y1=7+y*13
                draw.rounded_rectangle((x1,y1,x1+9,y1+9),radius=2,fill=c)
        return image

    def _start_tray(self):
        menu=pystray.Menu(
            pystray.MenuItem("打开可视化界面",lambda _i,_m:self._queue_ui(("show_window",)),default=True),
            pystray.MenuItem("完全退出程序",lambda _i,_m:self._queue_ui(("quit_app",)))
        )
        self.tray_icon=pystray.Icon("LaunchpadStudio",self._tray_image(),PRODUCT_TITLE,menu)
        threading.Thread(target=self._run_tray,name="TrayIcon",daemon=True).start()

    def _run_tray(self):
        try:self.tray_icon.run()
        except Exception:logging.error("Tray icon failed",exc_info=True)

    def _hide_to_tray(self):
        self.withdraw(); self.set_status("后台运行中")
        if not getattr(self,"tray_notice_shown",False):
            self.tray_notice_shown=True
            try:self.tray_icon.notify("MIDI、宏和灯效继续在后台运行。右键图标可重新打开或完全退出。","Launchpad Studio 已收起")
            except Exception:pass

    def _show_window(self):
        self.deiconify(); self.state("normal"); self.lift()
        try:self.focus_force()
        except Exception:pass

    def _close(self):
        if self._closing:return
        self._closing=True; self._stop_all(); self.settings_store.data["brightness"]=round(self.brightness.get()); self.settings_store.save()
        for device in {id(device):device for device in self.launchpads.values()}.values():device.disconnect()
        if self.remote_tick_job:
            try:self.after_cancel(self.remote_tick_job)
            except Exception:pass
        if self.remote_server:self.remote_server.stop()
        if hasattr(self,"system_media"):self.system_media.stop()
        try:self.tray_icon.stop()
        except Exception:pass
        self.destroy()

    def report_callback_exception(self, exc, value, tb):
        logging.error("Tk callback failed", exc_info=(exc,value,tb))
        try: messagebox.showerror("Launchpad Studio 发生错误",f"{value}\n\n详细日志：{LOG_DIR / 'crash.log'}")
        except Exception: pass


if __name__ == "__main__":
    os.chdir(ROOT)
    if "--self-test" in sys.argv:
        from core.launchpad import MODELS
        for model in MODELS:
            addresses=[((0xB0 if model.address_kind=="legacy" and xy[1]==0 else 0x90),model.address(*xy)) for xy in model.pads]
            if len(addresses)!=len(set(addresses)):raise RuntimeError(f"Duplicate MIDI addresses: {model.name}")
        if len(clock_frame(datetime.now(),0,(1,2,3),(4,5,6)))!=80:raise RuntimeError("Frame renderer failed")
        sys.exit(0)
    if not _single_instance():sys.exit(0)
    def _thread_error(args):
        logging.error("Background thread failed",exc_info=(args.exc_type,args.exc_value,args.exc_traceback))
    threading.excepthook=_thread_error
    app=LaunchpadStudio()
    app.mainloop()
