from __future__ import annotations

import logging
from pathlib import Path
import queue
import sys
import time

import numpy as np

from .audio_engine import LiveAudio
from .vj_engine import RealtimeMusicFeatures, VJ_STYLES, native_led_pixels, vj_colors
from .vj_shaders import FRAGMENT, MAP, PRESENT, VERTEX


def run_vj(config,commands,events,stop_event):
    """Qt owns its event loop in a child process; Tk never touches OpenGL."""
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
    import moderngl

    log_path=Path(config["log_path"]); log_path.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=log_path,level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s",force=True)
    import faulthandler
    fault_log=log_path.open("a",encoding="utf-8"); faulthandler.enable(fault_log)

    def emit(message):
        try:events.put_nowait(message)
        except queue.Full:
            try:events.get_nowait()
            except queue.Empty:pass
            try:events.put_nowait(message)
            except queue.Full:pass

    fmt=QSurfaceFormat(); fmt.setVersion(3,3); fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setAlphaBufferSize(8); fmt.setDepthBufferSize(0); fmt.setStencilBufferSize(0); fmt.setSwapInterval(0)
    QSurfaceFormat.setDefaultFormat(fmt)
    application=QApplication([]); application.setQuitOnLastWindowClosed(False)

    class OutputCanvas(QOpenGLWidget):
        def __init__(self,session,parent):
            super().__init__(parent); self.session=session; self.ctx=None; self.resources=[]
            self.buffer=None; self.texture=None; self.map_buffer=None; self.map_texture=None
            self.buffer_size=None; self.map_size=None; self.frames=0; self.last_map=0.
            self.setFormat(fmt)

        def initializeGL(self):
            try:
                self.ctx=moderngl.create_context(require=330)
                self.program=self.ctx.program(vertex_shader=VERTEX,fragment_shader=FRAGMENT)
                self.present=self.ctx.program(vertex_shader=VERTEX,fragment_shader=PRESENT)
                self.mapper=self.ctx.program(vertex_shader=VERTEX,fragment_shader=MAP)
                self.vao=self.ctx.vertex_array(self.program,[]); self.present_vao=self.ctx.vertex_array(self.present,[])
                self.map_vao=self.ctx.vertex_array(self.mapper,[])
                self.resources=[self.vao,self.present_vao,self.map_vao,self.program,self.present,self.mapper]
                self.context().aboutToBeDestroyed.connect(self.cleanup)
                logging.info("VJ GPU: %s",self.ctx.info.get("GL_RENDERER"))
            except Exception as exc:self.session.fail(f"GPU 初始化失败：{exc}")

        def cleanup(self):
            if not self.ctx:return
            self.makeCurrent()
            for resource in [self.buffer,self.texture,self.map_buffer,self.map_texture,*self.resources]:
                if resource:resource.release()
            self.buffer=self.texture=self.map_buffer=self.map_texture=None; self.resources=[]; self.ctx=None
            self.buffer_size=self.map_size=None
            self.doneCurrent()

        def paintGL(self):
            if not self.ctx or self.session.failed:return
            try:self.render()
            except Exception as exc:
                logging.exception("VJ frame failed"); self.session.fail(f"VJ 渲染失败：{exc}")

        def render(self,present=True):
            cfg=self.session.cfg; features=self.session.features; now=self.session.now
            size=(cfg["width"],cfg["height"])
            if self.buffer_size!=size:
                if self.buffer:self.buffer.release(); self.texture.release()
                self.texture=self.ctx.texture(size,4); self.texture.filter=(moderngl.LINEAR,moderngl.LINEAR)
                self.buffer=self.ctx.framebuffer(color_attachments=[self.texture]); self.buffer_size=size
            self.ctx.disable(moderngl.BLEND|moderngl.DEPTH_TEST|moderngl.CULL_FACE)
            self.buffer.use(); self.buffer.clear(0,0,0,0)
            uniforms={"resolution":size,"clock":self.session.motion,"energy":features["energy"],"bass":features["bass"],
                      "treble":features["treble"],"beat":features["beat"],"speed":cfg["speed"],"intensity":cfg["intensity"],
                      "detail":cfg["detail"],"scene":self.session.scene,"previous":self.session.previous,
                      "transition":min(1.,(now-self.session.changed_at)/1.5),"alpha":int(cfg["alpha"])}
            low,high=vj_colors(cfg,features)
            uniforms.update(lowColor=tuple(v/255 for v in low),highColor=tuple(v/255 for v in high))
            for key,value in uniforms.items():self.program[key].value=value
            self.program["bands"].write(np.asarray(features["bands"],dtype="f4").tobytes())
            self.vao.render(vertices=3)
            self.frames+=1
            # Downsample the real GPU image, not a separately generated LED effect.
            if cfg["map_launchpad"] and cfg["led_style"]=="原画采样" and now-self.last_map>=.05 and self is self.session.primary_canvas():
                map_size=tuple(cfg["output_size"])
                if map_size!=self.map_size:
                    if self.map_buffer:self.map_buffer.release(); self.map_texture.release()
                    self.map_texture=self.ctx.texture(map_size,3); self.map_buffer=self.ctx.framebuffer([self.map_texture]); self.map_size=map_size
                self.map_buffer.use(); self.texture.use(0); self.mapper["image"].value=0
                self.mapper["cellSize"].value=(1/map_size[0],1/map_size[1]); self.map_vao.render(vertices=3)
                rgb=np.frombuffer(self.map_buffer.read(components=3,alignment=1),dtype=np.uint8).reshape(map_size[1],map_size[0],3)[::-1].copy()
                emit({"pixels":rgb}); self.last_map=now; self.session.led_frames+=1
            if not present:return
            screen=self.ctx.detect_framebuffer(self.defaultFramebufferObject()); screen.use()
            screen.clear(0,0,0,0 if cfg["alpha"] else 1)
            target=(max(1,round(self.width()*self.devicePixelRatioF())),max(1,round(self.height()*self.devicePixelRatioF())))
            self.ctx.viewport=(0,0,*target); self.texture.use(0)
            self.present["image"].value=0; self.present["sourceSize"].value=size; self.present["targetSize"].value=target
            self.present_vao.render(vertices=3)

    class OutputWindow(QWidget):
        def __init__(self,session,key,screen=None):
            super().__init__(); self.session=session; self.key=key
            self.setWindowTitle("Launchpad Studio · VJ "+("预览 · F11 全屏 / Esc 关闭" if key=="preview" else key))
            if session.cfg["alpha"]:
                self.setWindowFlags(Qt.Window|Qt.FramelessWindowHint)
                self.setAttribute(Qt.WA_TranslucentBackground)
            layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
            self.canvas=OutputCanvas(session,self); layout.addWidget(self.canvas)
            aspect=session.cfg["width"]/session.cfg["height"]; available=application.primaryScreen().availableGeometry()
            width=min(800,available.width()*.75,available.height()*.75*aspect)
            self.resize(round(width),round(width/aspect))
            if screen:
                self.setWindowFlags(self.windowFlags()|Qt.FramelessWindowHint)
                self.setGeometry(screen.geometry()); self.show(); self.windowHandle().setScreen(screen); self.showFullScreen()
            else:self.show()
            self.setFocus()

        def keyPressEvent(self,event):
            if event.key()==Qt.Key_Escape:
                self.close()
            elif event.key()==Qt.Key_F11:
                self.showNormal() if self.isFullScreen() else self.showFullScreen()
            else:super().keyPressEvent(event)

        def mouseDoubleClickEvent(self,event):
            self.showNormal() if self.isFullScreen() else self.showFullScreen()

        def mousePressEvent(self,event):
            if not self.isFullScreen() and event.button()==Qt.LeftButton:self.windowHandle().startSystemMove()
            else:super().mousePressEvent(event)

        def closeEvent(self,event):
            self.canvas.cleanup(); self.session.windows.pop(self.key,None)
            self.deleteLater(); event.accept()
            if not self.session.windows and not self.session.rebuilding:stop_event.set()

    class Session:
        def __init__(self):
            self.cfg=dict(config); self.analyser=RealtimeMusicFeatures(); self.features=self.analyser.snapshot()
            self.windows={}; self.failed=False; self.rebuilding=False; self.scene=0; self.previous=0
            self.now=time.monotonic(); self.start_time=self.now; self.changed_at=self.now-2; self.next_scene=self.now+self.cfg["scene_seconds"]
            self.motion=0.; self.last_frame=self.now; self.next_frame=self.now; self.last_state=self.now; self.fps=0.
            self.last_led=0.; self.led_frames=0; self.led_style="停止"
            self.capture=LiveAudio(None,self.audio_status,self.audio_samples)
            self.audio_message="等待音频"; self.rebuild()
            self.capture.start(self.cfg["device"],"频谱","霓虹",1)
            self.timer=QTimer(); self.timer.setTimerType(Qt.PreciseTimer); self.timer.timeout.connect(self.tick); self.timer.start(4)
            application.screenRemoved.connect(lambda _screen:self.screens_changed())
            application.screenAdded.connect(lambda _screen:self.screens_changed())

        def audio_status(self,text):self.audio_message=text

        def audio_samples(self,samples,sr):self.analyser.feed(samples,sr,self.cfg["sensitivity"],self.cfg["threshold"])

        def fail(self,text):
            self.failed=True; emit({"error":text,"state":{"running":False}}); stop_event.set()

        def screens_changed(self):
            available={screen.name() for screen in application.screens()}
            self.cfg["screens"]=[key for key in self.cfg["screens"] if key in available]
            if not self.cfg["screens"]:self.cfg["preview"]=True
            self.rebuild()

        def rebuild(self):
            self.rebuilding=True
            for window in list(self.windows.values()):window.close()
            self.windows={}
            screens={screen.name():screen for screen in application.screens()}
            if self.cfg["preview"]:self.windows["preview"]=OutputWindow(self,"preview")
            for key in self.cfg["screens"]:
                if key in screens:self.windows[key]=OutputWindow(self,key,screens[key])
            self.rebuilding=False

        def primary_canvas(self):
            return next((w.canvas for w in self.windows.values() if not w.isMinimized()),next((w.canvas for w in self.windows.values()),None))

        def tick(self):
            if stop_event.is_set():application.quit(); return
            latest=None
            while True:
                try:latest=commands.get_nowait()
                except queue.Empty:break
            if latest:
                old=self.cfg; self.cfg=dict(latest)
                if old["device"]!=self.cfg["device"]:
                    self.analyser=RealtimeMusicFeatures()
                    try:self.capture.start(self.cfg["device"],"频谱","霓虹",1)
                    except Exception as exc:self.fail(str(exc)); return
                if any(old[key]!=self.cfg[key] for key in ("alpha","preview","screens")):self.rebuild()
            self.now=time.monotonic()
            self.features=self.analyser.snapshot()
            if self.cfg["map_launchpad"] and self.cfg["led_style"]!="原画采样" and self.now-self.last_led>=.05:
                pixels,self.led_style=native_led_pixels(self.cfg,self.features,self.motion,self.scene)
                emit({"pixels":pixels}); self.last_led=self.now; self.led_frames+=1
            if self.now<self.next_frame:return
            self.next_frame=max(self.next_frame+1/self.cfg["fps"],self.now)
            self.motion+=(self.now-self.last_frame)*(.7+self.features["energy"]*.3+min(1.,self.features["bpm"]/240))
            self.last_frame=self.now
            if self.cfg["style"]=="自动编排":
                if self.now>=self.next_scene:
                    pool=(2,3,5) if self.features["mood"]=="沉静" else (0,1,4,7) if self.features["mood"] in ("激昂","热烈") else (0,2,4,6)
                    scene=pool[(self.features["beats"]//4+round(self.motion))%len(pool)]
                    if scene==self.scene:scene=pool[(pool.index(scene)+1)%len(pool)]
                    self.previous=self.scene; self.scene=scene; self.changed_at=self.now
                    self.next_scene=self.now+self.cfg["scene_seconds"]
            else:
                selected=VJ_STYLES.index(self.cfg["style"])-1
                if selected!=self.scene:self.previous=self.scene; self.scene=selected; self.changed_at=self.now
            for window in list(self.windows.values()):
                canvas=window.canvas
                if window.isMinimized() and self.cfg["map_launchpad"] and self.cfg["led_style"]=="原画采样" and canvas is self.primary_canvas() and canvas.ctx:
                    try:
                        canvas.makeCurrent(); canvas.render(present=False); canvas.doneCurrent()
                    except Exception as exc:self.fail(f"后台 VJ 渲染失败：{exc}")
                else:canvas.update()
            if self.now-self.last_state>=.25:
                rendered=sum(w.canvas.frames for w in self.windows.values())
                self.fps=rendered/max(.001,self.now-self.last_state)/max(1,len(self.windows))
                for window in self.windows.values():window.canvas.frames=0
                state={"running":True,"starting":False,"fps":round(self.fps,1),"scene":VJ_STYLES[self.scene+1],
                       "led_style":self.led_style if self.cfg["led_style"]!="原画采样" else "原画采样",
                       "led_width":self.cfg["output_size"][0],"led_height":self.cfg["output_size"][1],
                       "led_fps":round(self.led_frames/max(.001,self.now-self.last_state),1),
                       "windows":list(self.windows),"audio_status":self.audio_message,"width":self.cfg["width"],"height":self.cfg["height"],
                       **{key:value for key,value in self.features.items() if key!="bands"}}
                emit({"state":state}); self.last_state=self.now; self.led_frames=0

    session=None
    try:
        session=Session.__new__(Session); session.__init__(); application.exec()
    except Exception as exc:
        logging.exception("VJ process failed"); emit({"error":str(exc),"state":{"running":False}})
    finally:
        if session:
            if hasattr(session,"capture"):session.capture.stop()
            session.rebuilding=True
            for window in list(session.windows.values()):window.close()
        emit({"state":{"running":False}})
