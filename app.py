from __future__ import annotations

import os
import json
from pathlib import Path
import ctypes
import faulthandler
import logging
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog, ttk
from PIL import Image, ImageDraw
import pystray

from core.launchpad import ALL_PADS, MODELS, LaunchpadDevice
from core.settings import AUDIO_DETAIL_DEFAULTS, VIDEO_DETAIL_DEFAULTS, Settings
from core.macros import MacroExecutor
from core.performance import PALETTES, PerformanceMonitor
from core.video_engine import VideoPlayer
from core.audio_engine import LiveAudio, MusicShow, audio_devices
from core.miniapps import SnakeGame, WhackAMole, calendar_frame, clock_frame, scrolling_text, weather_frame
from core.weather import WeatherService


FROZEN = bool(getattr(sys,"frozen",False))
BUNDLE_ROOT = Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
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
        hwnd=find(None,"Launchpad Studio") or find(None,"Launchpad Studio MK2")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd,9); ctypes.windll.user32.SetForegroundWindow(hwnd)
        return False
    return True
BG, PANEL, PANEL2 = "#0b0d12", "#121620", "#191e2a"
TEXT, MUTED, ACCENT, GOOD, BAD = "#f3f5fb", "#8992a7", "#7c5cff", "#34d399", "#fb7185"


class PadCanvas(tk.Canvas):
    def __init__(self, master, on_click, launchpad):
        super().__init__(master, bg=PANEL, highlightthickness=0, height=590, width=590)
        self.on_click = on_click
        self.launchpad = launchpad
        self.items, self.colors, self.selected = {}, {}, None
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<Button-1>", self._click)

    def _geometry(self):
        w, h = max(300, self.winfo_width()), max(300, self.winfo_height())
        pads = self.launchpad.pads
        min_x, max_x = min(x for x,_ in pads), max(x for x,_ in pads)
        min_y, max_y = min(y for _,y in pads), max(y for _,y in pads)
        cols, rows = max_x-min_x+1, max_y-min_y+1
        cell = min((w-44)/cols, (h-44)/rows)
        ox, oy = (w-cols*cell)/2-min_x*cell, (h-rows*cell)/2-min_y*cell
        return ox, oy, cell

    def draw(self):
        self.delete("all"); self.items.clear()
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
            if cell > 48:
                self.create_text((x1+x2)/2, (y1+y2)/2, text=self.launchpad.pad_label(x,y),
                                 fill="#ffffff" if sum(rgb)>250 else "#657087",
                                 font=("Segoe UI", 7))

    def _click(self, event):
        ox, oy, cell = self._geometry()
        x, y = int((event.x-ox)//cell), int((event.y-oy)//cell)
        if (x,y) in self.launchpad.pads:
            self.selected = (x,y); self.draw(); self.on_click(x,y)

    def set_frame(self, frame):
        self.colors = frame
        self.draw()


class LaunchpadStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.ui_events=queue.Queue(maxsize=24); self._closing=False
        self.title("Launchpad Studio")
        self.geometry("1280x820")
        self.minsize(1060, 700)
        self.configure(bg=BG)
        try: self.iconbitmap(BUNDLE_ROOT / "app.ico")
        except Exception: pass
        self.settings_store = Settings(ROOT / "data" / "settings.json")
        initial_model=self.settings_store.data.get("launchpad_model","auto")
        self.lp = LaunchpadDevice(self._hardware_pad, initial_model if initial_model != "auto" else "mk2")
        self._param_save_job=None; self._settings_save_job=None; self._parameter_clipboard=None
        self.macro_exec = MacroExecutor()
        self.performance = PerformanceMonitor()
        self.video = VideoPlayer(self.submit_frame, self.set_status, self._video_progress, self._video_finished)
        self.music = None
        self.live = None
        self.weather=WeatherService(); self.weather_data=None
        self.snake=SnakeGame(); self.mole=WhackAMole()
        self.utility_running=False; self.utility_job=None; self.utility_phase=0
        self.focus_deadline=None; self.focus_remaining=0; self.focus_paused=False
        self.mode = "性能监控"
        self.running_perf = False
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
        self.bind("<KeyPress>",self._utility_key)
        self._start_tray()
        self.after(16,self._drain_ui_events)
        self.after(3000,self._midi_watchdog)
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

    def _build_style(self):
        s = ttk.Style(self); s.theme_use("clam")
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
        s.configure("TEntry", fieldbackground=PANEL2, foreground=TEXT, insertcolor=TEXT,
                    bordercolor="#30384b")
        s.configure("TScale", background=PANEL, troughcolor="#292f40")

    def _build_ui(self):
        top = tk.Frame(self, bg=BG, height=72); top.pack(fill="x", padx=24, pady=(16,8)); top.pack_propagate(False)
        ttk.Label(top, text="Launchpad Studio", style="Title.TLabel").pack(side="left", pady=14)
        self.status_dot = tk.Label(top, text="●", bg=BG, fg=BAD, font=("Segoe UI", 13)); self.status_dot.pack(side="left", padx=(18,5))
        self.device_status = tk.Label(top, text="未连接", bg=BG, fg=MUTED, font=("Segoe UI", 9)); self.device_status.pack(side="left")
        ttk.Button(top, text="设备设置", command=self._device_dialog).pack(side="right", pady=12)
        ttk.Button(top, text="灯光测试", command=self._test_lights).pack(side="right", padx=8, pady=12)

        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=24, pady=(0,18))
        side = tk.Frame(body, bg=PANEL, width=188); side.pack(side="left", fill="y"); side.pack_propagate(False)
        tk.Label(side, text="模式", bg=PANEL, fg=MUTED, font=("Segoe UI",9,"bold")).pack(anchor="w", padx=18, pady=(22,10))
        self.mode_buttons = {}
        icons = {"性能监控":"▥", "宏按键":"⌘", "视频播放":"▶", "音乐演示":"♫", "实时拾音":"≋", "工具与游戏":"◈"}
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
        self.pad_canvas=PadCanvas(self.center,self._canvas_pad,self.lp); self.pad_canvas.pack(fill="both",expand=True,padx=8,pady=8)
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

    def _clear_page(self):
        for w in self.page.winfo_children(): w.destroy()
        self.page_canvas.yview_moveto(0)

    def _page_title(self, title, subtitle):
        ttk.Label(self.page,text=title,style="Title.TLabel").pack(anchor="w",pady=(4,3))
        tk.Label(self.page,text=subtitle,bg=BG,fg=MUTED,font=("Segoe UI",9),wraplength=310,justify="left").pack(anchor="w",pady=(0,18))

    def _card(self):
        f=tk.Frame(self.page,bg=PANEL2,padx=14,pady=12); f.pack(fill="x",pady=6); return f

    def _show_mode(self, name):
        previous={"视频播放":"video","音乐演示":"music","实时拾音":"live"}.get(getattr(self,"mode",None))
        if previous and self._detail_snapshot(previous):
            if self._param_save_job:
                try:self.after_cancel(self._param_save_job)
                except Exception:pass
                self._param_save_job=None
            self._save_detail_now(previous)
        if getattr(self,"mode",None)=="工具与游戏":self._stop_utility(clear=False)
        self.video.stop()
        if self.music: self.music.stop()
        if self.live: self.live.stop()
        self.running_perf=False; self.mode=name; self._clear_page()
        for n,b in self.mode_buttons.items(): b.configure(bg=PANEL2 if n==name else PANEL,fg="#c8bfff" if n==name else TEXT)
        {"性能监控":self._page_performance,"宏按键":self._page_macros,"视频播放":self._page_video,
         "音乐演示":self._page_music,"实时拾音":self._page_live,"工具与游戏":self._page_utilities}[name]()

    def _page_performance(self):
        self._page_title("性能监控","负载映射到 8×8 灯柱；右侧圆键显示当前最高硬件温度。")
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
        ttk.Button(self.page,text="停止",command=self._stop_all).pack(fill="x")

    def _start_perf(self):
        self.running_perf=True; self.set_status("性能监控运行中 · 2 Hz"); self._perf_tick()

    def _perf_tick(self):
        if not self.running_perf or self.mode!="性能监控": return
        stats=self.performance.sample()
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
        self.apply_frame(self.performance.frame(stats,self.palette_var.get(),self.brightness.get()/100))
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
        ttk.Combobox(self.page,textvariable=self.action_var,state="readonly",values=["热键","输入文字","打开文件/程序","打开网址","执行命令","媒体控制","按键序列"]).pack(fill="x")
        tk.Label(self.page,text="内容",bg=BG,fg=MUTED).pack(anchor="w",pady=(12,4))
        self.macro_value=tk.StringVar(); ttk.Entry(self.page,textvariable=self.macro_value).pack(fill="x")
        tk.Label(self.page,text="示例：CTRL+SHIFT+S；PLAY；C:\\Windows\\notepad.exe",bg=BG,fg="#5f687c",font=("Segoe UI",8),wraplength=310,justify="left").pack(anchor="w",pady=4)
        self.macro_color="#7c5cff"
        ttk.Button(self.page,text="选择此按键颜色",command=self._pick_macro_color).pack(fill="x",pady=(12,6))
        ttk.Button(self.page,text="保存按键",style="Accent.TButton",command=self._save_macro).pack(fill="x",pady=6)
        ttk.Button(self.page,text="测试执行",command=self._test_macro).pack(fill="x")
        self._load_macro_form(*self.selected_pad); self._render_macro_profile()

    def _macro_key(self,x,y):
        return self.lp.macro_key(x,y)

    def _macro_get(self,x,y):
        macros=self.settings_store.data["macros"]
        # The numeric fallback preserves existing MK2 profiles after migration.
        return macros.get(self._macro_key(x,y),macros.get(str(self.lp.pad_id(x,y)),{}))

    def _load_macro_form(self,x,y):
        self.selected_pad=(x,y); key=self._macro_key(x,y); macro=self._macro_get(x,y)
        if hasattr(self,"pad_name"): self.pad_name.configure(text=f"当前按键：{key}")
        if hasattr(self,"action_var"): self.action_var.set(macro.get("action","热键")); self.macro_value.set(macro.get("value","")); self.macro_color=macro.get("color","#7c5cff")

    def _pick_macro_color(self):
        value=colorchooser.askcolor(self.macro_color,title="按键颜色")[1]
        if value: self.macro_color=value

    def _save_macro(self):
        key=self._macro_key(*self.selected_pad); self.settings_store.data["macros"][key]={"action":self.action_var.get(),"value":self.macro_value.get().strip(),"color":self.macro_color}
        self.settings_store.save(); self._render_macro_profile(); self.set_status(f"按键 {key} 已保存")

    def _test_macro(self):
        macro=self._macro_get(*self.selected_pad)
        if macro: self.macro_exec.execute(macro)

    def _render_macro_profile(self):
        frame={xy:(0,0,0) for xy in self.lp.pads}
        for xy in self.lp.pads:
            m=self._macro_get(*xy)
            if m:
                h=m.get("color","#7c5cff").lstrip("#"); frame[xy]=tuple(int(h[i:i+2],16) for i in (0,2,4))
        self.apply_frame(frame)

    def _page_video(self):
        self._page_title("视频像素播放器","播放列表、拖动定位、变速、循环与实时像素滤镜。")
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
        ttk.Button(self.page,text="停止",command=self._stop_all).pack(fill="x",pady=(10,18))

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
        self.video_path=self.video_playlist[self.video_index]
        self.video_list.selection_clear(0,"end"); self.video_list.selection_set(self.video_index); self.video_list.see(self.video_index)
        params=self._video_params(); self.video.start(self.video_path,self.video_fps.get(),self.brightness.get()/100,
              params["saturation"],self._rate(self.video_rate.get()),0,self.video_effect.get(),params)
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
        if hasattr(self,"video_effect"):self.video.set_effect(self.video_effect.get(),self._video_params())
        self._schedule_param_save("video")

    def _page_music(self):
        self._page_title("音乐灯光播放器","音频播放、变速与灯光采样使用同一时间轴，拖动后保持同步。")
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
        ttk.Button(self.page,text="停止",command=self._stop_all).pack(fill="x",pady=(10,18))

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
                if not self.music:self.music=MusicShow(self.submit_frame,self.set_status,self._audio_progress,self._audio_finished)
                a=self.music.analyse(p); self.after(0,lambda:self.analysis_label.configure(text=f"BPM {a.bpm}  ·  {a.mood}  ·  {a.genre}\n能量 {a.energy*100:.0f}%"))
            except Exception as e:self.after(0,lambda err=str(e):self.analysis_label.configure(text=f"分析失败：{err}"))
        threading.Thread(target=work,daemon=True).start()

    def _start_music(self):
        sel=self.audio_list.curselection() if hasattr(self,"audio_list") else ()
        if sel:self.audio_index=sel[0]
        if not (0<=self.audio_index<len(self.audio_playlist)):return messagebox.showinfo("Launchpad Studio","请先添加音频。")
        self.audio_path=self.audio_playlist[self.audio_index]; self.audio_list.selection_clear(0,"end"); self.audio_list.selection_set(self.audio_index); self.audio_list.see(self.audio_index)
        try:
            if not self.music:self.music=MusicShow(self.submit_frame,self.set_status,self._audio_progress,self._audio_finished)
            a=self.music.analyse(self.audio_path); self.analysis_label.configure(text=f"BPM {a.bpm}  ·  {a.mood}  ·  {a.genre}\n能量 {a.energy*100:.0f}%")
            self.music.set_volume(self.audio_volume.get()/100)
            self.music.start(self.audio_path,self.music_style.get(),self.palette_var.get(),self.brightness.get()/100,self._visual_params(self.music_visual_vars),0,self._rate(self.audio_rate.get()),self.audio_loop.get()=="单曲循环")
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
        if self.music and hasattr(self,"music_visual_vars"):self.music.set_visual(self.music_style.get(),self.palette_var.get(),self.brightness.get()/100,self._visual_params(self.music_visual_vars))
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
        ttk.Button(self.page,text="停止",command=self._stop_all).pack(fill="x")

    def _start_live(self):
        if not self.live_devices:return messagebox.showerror("没有输入设备","未发现可用的麦克风或回放输入设备。")
        idx=self.live_combo.current(); device=self.live_devices[max(0,idx)][0]
        try:
            if not self.live:self.live=LiveAudio(self.submit_frame,self.set_status)
            self.live.start(device,self.live_style.get(),self.palette_var.get(),self.brightness.get()/100,self._visual_params(self.live_visual_vars))
        except Exception as e:messagebox.showerror("拾音启动失败",str(e))

    def _update_live_visual(self):
        if self.live and hasattr(self,"live_visual_vars"):self.live.set_visual(self.live_style.get(),self.palette_var.get(),self.brightness.get()/100,self._visual_params(self.live_visual_vars))
        self._schedule_param_save("live")

    def _live_device_changed(self):
        self.settings_store.data["live_device"]=self.live_device.get(); self._schedule_settings_save()

    def _page_utilities(self):
        self._page_title("工具与解压游戏","让 Launchpad 在桌面常驻时也有用：时间、天气、专注提醒和可直接按键游玩的小游戏。")
        cfg=self.settings_store.data["utilities"]
        tk.Label(self.page,text="选择功能",bg=BG,fg=MUTED).pack(anchor="w",pady=(2,4))
        choices=["数字时钟","日历","天气","专注计时器","贪吃蛇","打地鼠"]
        self.utility_choice=tk.StringVar(value=cfg.get("selected","数字时钟"))
        combo=ttk.Combobox(self.page,textvariable=self.utility_choice,state="readonly",values=choices); combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>",lambda _e:self._utility_selection_changed())
        self.utility_options=tk.Frame(self.page,bg=BG); self.utility_options.pack(fill="x",pady=(10,0))
        self._build_utility_options()

    def _utility_selection_changed(self):
        self._stop_utility(clear=False)
        self.settings_store.data["utilities"]["selected"]=self.utility_choice.get(); self.settings_store.save()
        self._build_utility_options()

    def _build_utility_options(self):
        for widget in self.utility_options.winfo_children():widget.destroy()
        choice=self.utility_choice.get(); cfg=self.settings_store.data["utilities"]
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
        else:
            instructions="方向键控制；Launchpad 顶排前四键依次为左、上、下、右。" if choice=="贪吃蛇" else "在亮起的方块熄灭前按下它，点错或超时五次结束。"
            tk.Label(self.utility_options,text=instructions,bg=BG,fg=MUTED,wraplength=300,justify="left").pack(anchor="w",pady=5)
            self.utility_info=tk.Label(self.utility_options,text="得分 0",bg=PANEL2,fg=TEXT,font=("Segoe UI Semibold",16),padx=12,pady=10); self.utility_info.pack(fill="x",pady=6)
        ttk.Button(self.utility_options,text="开始 / 重新开始",style="Accent.TButton",command=self._start_utility).pack(fill="x",pady=(10,5))
        ttk.Button(self.utility_options,text="停止并熄灯",command=lambda:self._stop_utility(True)).pack(fill="x")

    def _utility_colors(self):
        low,high=PALETTES.get(self.palette_var.get(),PALETTES["霓虹"])
        amount=self.brightness.get()/100
        return tuple(round(v*amount) for v in low),tuple(round(v*amount) for v in high)

    def _start_utility(self):
        self._stop_utility(clear=False); choice=self.utility_choice.get(); cfg=self.settings_store.data["utilities"]
        self.utility_running=True; self.utility_phase=0
        if choice=="天气":
            city=self.weather_city.get().strip() or "北京"; cfg["weather_city"]=city; self.settings_store.save()
            self.utility_info.configure(text="正在获取天气…"); self.set_status(f"正在查询 {city} 天气")
            threading.Thread(target=self._weather_worker,args=(city,),daemon=True,name="WeatherFetch").start()
        elif choice=="专注计时器":
            minutes=max(1,min(180,int(self.focus_minutes.get()))); cfg["focus_minutes"]=minutes; self.settings_store.save()
            self.focus_remaining=minutes*60; self.focus_deadline=time.monotonic()+self.focus_remaining; self.focus_paused=False
        elif choice=="贪吃蛇":self.snake.reset()
        elif choice=="打地鼠":self.mole.reset(); self.mole_first_tick=True
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
        if not self.utility_running or self.mode!="工具与游戏":return
        choice=self.utility_choice.get(); low,high=self._utility_colors(); now=datetime.now(); delay=500
        if choice=="数字时钟":
            self.utility_info.configure(text=now.strftime("%H:%M:%S")); frame=clock_frame(now,self.utility_phase,low,high); delay=500
        elif choice=="日历":
            weekdays="一二三四五六日"; self.utility_info.configure(text=f"{now:%Y年%m月%d日} · 星期{weekdays[now.weekday()]}")
            frame=calendar_frame(now,self.utility_phase,low,high); delay=700
        elif choice=="天气":
            frame=weather_frame(self.weather_data["code"],self.weather_data["temperature"],low,high) if self.weather_data else scrolling_text("----",self.utility_phase,low,high); delay=700
        elif choice=="专注计时器":
            if not self.focus_paused and self.focus_deadline:self.focus_remaining=max(0,int(self.focus_deadline-time.monotonic()+.999))
            minutes,seconds=divmod(self.focus_remaining,60); value=f"{minutes:02d}:{seconds:02d}"
            self.utility_info.configure(text=value); frame=scrolling_text(value,self.utility_phase,low,high); delay=500
            if self.focus_remaining<=0:
                self.utility_running=False; self.set_status("专注计时完成")
                try:self.tray_icon.notify("休息一下吧，专注计时已经完成。","Launchpad Studio")
                except Exception:pass
        elif choice=="贪吃蛇":
            alive=self.snake.tick(); frame=self.snake.frame(); high_score=max(self.settings_store.data["utilities"].get("snake_high_score",0),self.snake.score)
            self.utility_info.configure(text=f"得分 {self.snake.score} · 最高 {high_score}"); delay=max(110,300-self.snake.score*10)
            if not alive:
                self.settings_store.data["utilities"]["snake_high_score"]=high_score; self.settings_store.save(); self.utility_running=False; self.set_status("贪吃蛇游戏结束")
        else:
            if not getattr(self,"mole_first_tick",False):self.mole.timeout()
            self.mole_first_tick=False; frame=self.mole.frame(); high_score=max(self.settings_store.data["utilities"].get("mole_high_score",0),self.mole.score)
            self.utility_info.configure(text=f"得分 {self.mole.score} · 失误 {self.mole.misses}/5 · 最高 {high_score}"); delay=max(280,850-self.mole.score*22)
            if not self.mole.running:
                self.settings_store.data["utilities"]["mole_high_score"]=high_score; self.settings_store.save(); self.utility_running=False; self.set_status("打地鼠游戏结束")
        self.apply_frame(frame); self.utility_phase+=1
        if self.utility_running:self.utility_job=self.after(delay,self._utility_tick)

    def _pause_focus(self):
        if self.utility_choice.get()!="专注计时器" or not self.utility_running:return
        if self.focus_paused:
            self.focus_deadline=time.monotonic()+self.focus_remaining; self.focus_paused=False; self.set_status("专注计时继续")
        else:
            self.focus_remaining=max(0,int(self.focus_deadline-time.monotonic()+.999)); self.focus_paused=True; self.set_status("专注计时已暂停")

    def _reset_focus(self):
        self._stop_utility(clear=True); self.focus_remaining=max(1,int(self.focus_minutes.get()))*60
        if hasattr(self,"utility_info"):self.utility_info.configure(text=f"{self.focus_remaining//60:02d}:00")

    def _stop_utility(self,clear=False):
        self.utility_running=False
        if self.utility_job:
            try:self.after_cancel(self.utility_job)
            except Exception:pass
            self.utility_job=None
        if clear:self.apply_frame({xy:(0,0,0) for xy in ALL_PADS}); self.set_status("工具/游戏已停止")

    def _utility_key(self,event):
        if self.mode!="工具与游戏" or not self.utility_running or self.utility_choice.get()!="贪吃蛇":return
        direction={"Left":(-1,0),"Up":(0,-1),"Down":(0,1),"Right":(1,0)}.get(event.keysym)
        if direction:self.snake.steer(direction)

    def _utility_pad(self,x,y):
        if not self.utility_running:return
        choice=self.utility_choice.get()
        if choice=="贪吃蛇":
            directions={0:(-1,0),1:(0,-1),2:(0,1),3:(1,0)}
            if y==0 and x in directions:self.snake.steer(directions[x])
            elif 0<=x<8 and 1<=y<=8:
                hx,hy=self.snake.snake[0]; dx,dy=x-hx,y-hy
                self.snake.steer((1 if dx>0 else -1,0) if abs(dx)>abs(dy) else (0,1 if dy>0 else -1))
        elif choice=="打地鼠" and 0<=x<8 and 1<=y<=8:
            hit=self.mole.hit((x,y)); self.set_status("命中！" if hit else "没有打中")
            self.apply_frame(self.mole.frame())

    def _canvas_pad(self,x,y):
        if self.mode=="宏按键":self._load_macro_form(x,y)
        elif self.mode=="工具与游戏":self._utility_pad(x,y)

    def _hardware_pad(self,x,y,pressed,velocity):
        self.after(0,lambda:self._handle_pad_ui(x,y,pressed))

    def _handle_pad_ui(self,x,y,pressed):
        if not pressed:return
        self.pad_canvas.selected=(x,y); self.pad_canvas.draw()
        if self.mode=="宏按键":
            macro=self._macro_get(x,y)
            if macro:self.macro_exec.execute(macro); self.set_status(f"已执行按键 {self.lp.pad_label(x,y)} · {macro['action']}")
        elif self.mode=="工具与游戏":self._utility_pad(x,y)

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
        if self.mode=="音乐演示" and hasattr(self,"music_visual_vars"):self._update_music_visual()
        elif self.mode=="实时拾音" and hasattr(self,"live_visual_vars"):self._update_live_visual()
        elif self.mode=="视频播放" and hasattr(self,"video_vars"):self._update_video_effect()

    def _pick_global_color(self):
        value=colorchooser.askcolor(self.custom_color,title="整体主色")[1]
        if value:
            self.custom_color=value; self.settings_store.data["custom_color"]=value; h=value.lstrip("#"); rgb=tuple(int(h[i:i+2],16) for i in (0,2,4)); PALETTES["自定义"]=(tuple(int(v*.18) for v in rgb),rgb); self.palette_var.set("自定义"); self._palette_changed()

    def _refresh_midi(self):
        self.midi_inputs,self.midi_outputs=self.lp.devices()
        if not self.lp.connected:
            ins=[i for i,n in enumerate(self.midi_inputs) if "launchpad" in n.casefold()]
            outs=[i for i,n in enumerate(self.midi_outputs) if "launchpad" in n.casefold()]
            if ins and outs:
                try:self.lp.connect(ins[0],outs[0],self.settings_store.data.get("launchpad_model","auto")); self._connected_ui()
                except Exception as e:self.set_status(f"自动连接失败：{e}")

    def _midi_watchdog(self):
        if self._closing:return
        if not self.lp.connected:
            try:self._refresh_midi()
            except Exception:logging.debug("MIDI reconnect check failed",exc_info=True)
        self.after(3000,self._midi_watchdog)

    def _device_dialog(self):
        self._refresh_midi(); win=tk.Toplevel(self); win.title("MIDI 设备"); win.geometry("430x350"); win.configure(bg=BG); win.transient(self); win.grab_set()
        tk.Label(win,text="Launchpad MIDI 连接",bg=BG,fg=TEXT,font=("Segoe UI Semibold",15)).pack(anchor="w",padx=20,pady=(18,14))
        model_values=["自动识别"]+[m.name for m in MODELS]
        saved_key=self.settings_store.data.get("launchpad_model","auto")
        modelvar=tk.StringVar(value="自动识别" if saved_key=="auto" else next((m.name for m in MODELS if m.key==saved_key),"自动识别"))
        tk.Label(win,text="设备型号",bg=BG,fg=MUTED).pack(anchor="w",padx=20); ttk.Combobox(win,textvariable=modelvar,values=model_values,state="readonly").pack(fill="x",padx=20,pady=(3,10))
        tk.Label(win,text="输入端口",bg=BG,fg=MUTED).pack(anchor="w",padx=20); invar=tk.StringVar(value=next((n for n in self.midi_inputs if "Launchpad" in n),self.midi_inputs[0] if self.midi_inputs else "")); inc=ttk.Combobox(win,textvariable=invar,values=self.midi_inputs,state="readonly"); inc.pack(fill="x",padx=20,pady=(3,10))
        tk.Label(win,text="输出端口",bg=BG,fg=MUTED).pack(anchor="w",padx=20); outvar=tk.StringVar(value=next((n for n in self.midi_outputs if "Launchpad" in n),self.midi_outputs[0] if self.midi_outputs else "")); outc=ttk.Combobox(win,textvariable=outvar,values=self.midi_outputs,state="readonly"); outc.pack(fill="x",padx=20,pady=(3,14))
        def connect():
            key=next((m.key for m in MODELS if m.name==modelvar.get()),"auto")
            try:
                self.lp.connect(self.midi_inputs.index(invar.get()),self.midi_outputs.index(outvar.get()),key)
                self.settings_store.data["launchpad_model"]=key; self.settings_store.save()
                self._connected_ui(); win.destroy()
            except Exception as e:messagebox.showerror("连接失败",str(e),parent=win)
        ttk.Button(win,text="连接",style="Accent.TButton",command=connect).pack(fill="x",padx=20)

    def _connected_ui(self):
        model=self.lp.model
        self.status_dot.configure(fg=GOOD); self.device_status.configure(text=f"{model.name} 已连接",fg=GOOD)
        self.model_footer.configure(text=f"{model.name} · {len(model.pads)} LEDs")
        self.pad_canvas.colors={xy:(0,0,0) for xy in model.pads}; self.pad_canvas.selected=None; self.pad_canvas.draw()
        self.set_status(f"真机已连接 · {len(model.pads)} LEDs · {model.name}")

    def _test_lights(self):
        if not self.lp.connected:return self._device_dialog()
        self.lp.test_pattern(); self.pad_canvas.set_frame(self.lp.colors); self.set_status("RGB 全键灯光测试")

    def submit_frame(self,frame):
        if threading.current_thread() is threading.main_thread():self.apply_frame(frame)
        else:self._queue_ui(("frame",frame))

    def apply_frame(self,frame):
        adapted=dict(frame)
        # Pro models add left and bottom control rows. Mirror the nearest content
        # so every physical LED participates in every existing mode.
        for x,y in self.lp.pads:
            if (x,y) in adapted:continue
            if x==-1:adapted[(x,y)]=frame.get((0,y),(0,0,0))
            elif y==9:adapted[(x,y)]=frame.get((x,8),(0,0,0))
            else:adapted[(x,y)]=(0,0,0)
        adapted={xy:adapted.get(xy,(0,0,0)) for xy in self.lp.pads}
        self.current_frame=adapted; self.pad_canvas.set_frame(adapted)
        try:self.lp.set_frame(adapted)
        except Exception as e:
            logging.error("MIDI output failed",exc_info=True)
            self.lp.disconnect(clear=False); self.status_dot.configure(fg=BAD); self.device_status.configure(text="连接中断 · 正在重试",fg=BAD)
            self.set_status(f"MIDI 输出错误：{e}；将自动重连")

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
        latest_frame=None; latest_video=None; latest_audio=None; latest_weather=None; weather_error=None
        try:
            for _ in range(30):
                event=self.ui_events.get_nowait(); kind=event[0]
                if kind=="frame":latest_frame=event[1]
                elif kind=="status":self.status_var.set(event[1])
                elif kind=="video_progress":latest_video=event[1:]
                elif kind=="audio_progress":latest_audio=event[1:]
                elif kind=="video_finished":self._advance_video(1,True)
                elif kind=="audio_finished":self._advance_audio(1,True)
                elif kind=="weather_result":latest_weather=event[1]
                elif kind=="weather_error":weather_error=event[1]
                elif kind=="show_window":self._show_window()
                elif kind=="quit_app":self._close()
        except queue.Empty:pass
        if latest_frame is not None:self.apply_frame(latest_frame)
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

    def _stop_all(self):
        self.running_perf=False; self.video.stop()
        if self.music:self.music.stop()
        if self.live:self.live.stop()
        self._stop_utility(clear=False)
        self.set_status("已停止")

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
        self.tray_icon=pystray.Icon("LaunchpadStudio",self._tray_image(),"Launchpad Studio",menu)
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
        self._closing=True; self._stop_all(); self.settings_store.data["brightness"]=round(self.brightness.get()); self.settings_store.save(); self.lp.disconnect()
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
