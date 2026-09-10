from __future__ import annotations
import ctypes
import os
import subprocess
import threading
import time
import webbrowser


user32 = ctypes.WinDLL("user32", use_last_error=True)
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK = {
    "CTRL": 0x11, "CONTROL": 0x11, "ALT": 0x12, "SHIFT": 0x10, "WIN": 0x5B,
    "ENTER": 0x0D, "RETURN": 0x0D, "TAB": 0x09, "ESC": 0x1B, "ESCAPE": 0x1B,
    "SPACE": 0x20, "BACKSPACE": 0x08, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "PLAY": 0xB3, "PAUSE": 0xB3, "NEXT": 0xB0, "PREV": 0xB1,
    "VOLUMEUP": 0xAF, "VOLUMEDOWN": 0xAE, "MUTE": 0xAD,
}
VK.update({f"F{i}": 0x6F + i for i in range(1, 25)})
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040


def key_code(name: str) -> int:
    name = name.strip().upper()
    if name in VK:
        return VK[name]
    if len(name) == 1:
        return user32.VkKeyScanW(ord(name)) & 0xFF
    raise ValueError(f"Unknown key: {name}")


def tap_hotkey(spec: str):
    keys = [key_code(k) for k in spec.replace("-", "+").split("+") if k.strip()]
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)


def type_text(text: str):
    for char in text:
        code = ord(char)
        user32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
        user32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)


def mouse_action(value: str):
    action=value.strip().upper()
    flags={"左键":(MOUSEEVENTF_LEFTDOWN,MOUSEEVENTF_LEFTUP),"LEFT":(MOUSEEVENTF_LEFTDOWN,MOUSEEVENTF_LEFTUP),
           "右键":(MOUSEEVENTF_RIGHTDOWN,MOUSEEVENTF_RIGHTUP),"RIGHT":(MOUSEEVENTF_RIGHTDOWN,MOUSEEVENTF_RIGHTUP),
           "中键":(MOUSEEVENTF_MIDDLEDOWN,MOUSEEVENTF_MIDDLEUP),"MIDDLE":(MOUSEEVENTF_MIDDLEDOWN,MOUSEEVENTF_MIDDLEUP)}
    down,up=flags.get(action.replace("双击",""),flags.get(action,(MOUSEEVENTF_LEFTDOWN,MOUSEEVENTF_LEFTUP)))
    count=2 if "双击" in action or action=="DOUBLE" else 1
    for _ in range(count):
        user32.mouse_event(down,0,0,0,0); user32.mouse_event(up,0,0,0,0); time.sleep(.06)


def system_action(value: str):
    action=value.strip().upper()
    if action in ("锁定电脑","LOCK"):ctypes.windll.user32.LockWorkStation()
    elif action in ("截图","SCREENSHOT"):tap_hotkey("WIN+SHIFT+S")
    elif action in ("任务管理器","TASKMANAGER"):subprocess.Popen(["taskmgr.exe"])
    elif action in ("资源管理器","EXPLORER"):subprocess.Popen(["explorer.exe"])
    elif action in ("显示桌面","DESKTOP"):tap_hotkey("WIN+D")


def set_volume(value: str):
    percent=max(0,min(100,int(float(value))))
    for _ in range(50):tap_hotkey("VOLUMEDOWN")
    for _ in range(round(percent/2)):tap_hotkey("VOLUMEUP")


def combined_actions(value: str):
    for line in value.replace(";","\n").splitlines():
        if not line.strip():continue
        kind,_,payload=line.partition(":"); kind=kind.strip().casefold(); payload=payload.strip()
        if kind in ("热键","hotkey","key"):tap_hotkey(payload)
        elif kind in ("文字","text"):type_text(payload)
        elif kind in ("等待","wait","delay"):time.sleep(max(0,float(payload))/1000)
        elif kind in ("打开","open"):os.startfile(payload)
        elif kind in ("网址","url"):webbrowser.open(payload)
        elif kind in ("媒体","media"):tap_hotkey(payload)
        elif kind in ("鼠标","mouse"):mouse_action(payload)


class MacroExecutor:
    def execute(self, macro: dict):
        threading.Thread(target=self._run, args=(macro,), daemon=True).start()

    def _run(self, macro: dict):
        action = macro.get("action", "热键")
        value = macro.get("value", "")
        try:
            if action == "热键":
                tap_hotkey(value)
            elif action == "输入文字":
                type_text(value)
            elif action == "打开文件/程序":
                os.startfile(value)
            elif action == "打开网址":
                webbrowser.open(value)
            elif action == "执行命令":
                subprocess.Popen(value, shell=True)
            elif action == "PowerShell":
                subprocess.Popen(["powershell.exe","-NoProfile","-WindowStyle","Hidden","-Command",value],creationflags=subprocess.CREATE_NO_WINDOW)
            elif action == "媒体控制":
                tap_hotkey(value)
            elif action == "按键序列":
                for item in value.split(","):
                    tap_hotkey(item.strip())
                    time.sleep(0.08)
            elif action == "鼠标操作":
                mouse_action(value)
            elif action == "系统操作":
                system_action(value)
            elif action == "设置音量":
                set_volume(value)
            elif action == "组合动作":
                combined_actions(value)
        except Exception:
            # UI owns notifications; failed macros must never stop MIDI input.
            pass
