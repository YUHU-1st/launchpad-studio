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
            elif action == "媒体控制":
                tap_hotkey(value)
            elif action == "按键序列":
                for item in value.split(","):
                    tap_hotkey(item.strip())
                    time.sleep(0.08)
        except Exception:
            # UI owns notifications; failed macros must never stop MIDI input.
            pass
