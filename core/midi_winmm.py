"""Small dependency-free Windows MIDI wrapper (WinMM)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
import time


if not hasattr(ctypes, "WinDLL"):
    raise RuntimeError("Launchpad Studio MIDI backend requires Windows")

winmm = ctypes.WinDLL("winmm")
DWORD_PTR = ctypes.c_size_t
HMIDIOUT = wintypes.HANDLE
HMIDIIN = wintypes.HANDLE
MMSYSERR_NOERROR = 0
CALLBACK_FUNCTION = 0x00030000
MIM_DATA = 0x3C3


class MIDIOUTCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.UINT), ("szPname", wintypes.WCHAR * 32),
                ("wTechnology", wintypes.WORD), ("wVoices", wintypes.WORD),
                ("wNotes", wintypes.WORD), ("wChannelMask", wintypes.WORD),
                ("dwSupport", wintypes.DWORD)]


class MIDIINCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.UINT), ("szPname", wintypes.WCHAR * 32),
                ("dwSupport", wintypes.DWORD)]


class MIDIHDR(ctypes.Structure):
    _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD),
                ("dwBytesRecorded", wintypes.DWORD), ("dwUser", DWORD_PTR),
                ("dwFlags", wintypes.DWORD), ("lpNext", ctypes.c_void_p),
                ("reserved", DWORD_PTR), ("dwOffset", wintypes.DWORD),
                ("dwReserved", DWORD_PTR * 8)]


winmm.midiOutGetNumDevs.restype = wintypes.UINT
winmm.midiInGetNumDevs.restype = wintypes.UINT
winmm.midiOutGetDevCapsW.argtypes = [wintypes.UINT, ctypes.POINTER(MIDIOUTCAPSW), wintypes.UINT]
winmm.midiInGetDevCapsW.argtypes = [wintypes.UINT, ctypes.POINTER(MIDIINCAPSW), wintypes.UINT]
winmm.midiOutOpen.argtypes = [ctypes.POINTER(HMIDIOUT), wintypes.UINT, DWORD_PTR, DWORD_PTR, wintypes.DWORD]
winmm.midiInOpen.argtypes = [ctypes.POINTER(HMIDIIN), wintypes.UINT, DWORD_PTR, DWORD_PTR, wintypes.DWORD]


def output_devices() -> list[str]:
    result = []
    for idx in range(winmm.midiOutGetNumDevs()):
        caps = MIDIOUTCAPSW()
        if winmm.midiOutGetDevCapsW(idx, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            result.append(caps.szPname)
    return result


def input_devices() -> list[str]:
    result = []
    for idx in range(winmm.midiInGetNumDevs()):
        caps = MIDIINCAPSW()
        if winmm.midiInGetDevCapsW(idx, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            result.append(caps.szPname)
    return result


class MidiOut:
    def __init__(self):
        self.handle = HMIDIOUT()
        self.lock = threading.Lock()

    def open(self, index: int):
        self.close()
        result = winmm.midiOutOpen(ctypes.byref(self.handle), index, 0, 0, 0)
        if result != MMSYSERR_NOERROR:
            raise OSError(f"Cannot open MIDI output (WinMM error {result})")

    def short(self, status: int, data1: int, data2: int):
        if not self.handle:
            return
        message = (status & 0xFF) | ((data1 & 0x7F) << 8) | ((data2 & 0x7F) << 16)
        with self.lock:
            winmm.midiOutShortMsg(self.handle, message)

    def sysex(self, data: bytes):
        if not self.handle:
            return
        buffer = ctypes.create_string_buffer(data)
        header = MIDIHDR(ctypes.cast(buffer, ctypes.c_void_p), len(data), len(data), 0, 0, None, 0, 0)
        with self.lock:
            result = winmm.midiOutPrepareHeader(self.handle, ctypes.byref(header), ctypes.sizeof(header))
            if result:
                raise OSError(f"Cannot prepare SysEx (WinMM error {result})")
            result = winmm.midiOutLongMsg(self.handle, ctypes.byref(header), ctypes.sizeof(header))
            if result:
                winmm.midiOutUnprepareHeader(self.handle, ctypes.byref(header), ctypes.sizeof(header))
                raise OSError(f"Cannot send SysEx (WinMM error {result})")
            deadline = time.monotonic() + 0.5
            while not (header.dwFlags & 0x1) and time.monotonic() < deadline:
                time.sleep(0.001)
            winmm.midiOutUnprepareHeader(self.handle, ctypes.byref(header), ctypes.sizeof(header))

    def reset(self):
        if self.handle:
            winmm.midiOutReset(self.handle)

    def close(self):
        if self.handle:
            self.reset()
            winmm.midiOutClose(self.handle)
            self.handle = HMIDIOUT()


MIDIINPROC = ctypes.WINFUNCTYPE(None, HMIDIIN, wintypes.UINT, DWORD_PTR, DWORD_PTR, DWORD_PTR)


class MidiIn:
    def __init__(self, callback=None):
        self.handle = HMIDIIN()
        self.callback = callback
        self._proc = MIDIINPROC(self._dispatch)

    def _dispatch(self, _handle, msg, _instance, param1, _param2):
        if msg == MIM_DATA and self.callback:
            status = param1 & 0xFF
            data1 = (param1 >> 8) & 0x7F
            data2 = (param1 >> 16) & 0x7F
            try:
                self.callback(status, data1, data2)
            except Exception:
                pass

    def open(self, index: int):
        self.close()
        result = winmm.midiInOpen(ctypes.byref(self.handle), index,
                                  ctypes.cast(self._proc, ctypes.c_void_p).value, 0, CALLBACK_FUNCTION)
        if result != MMSYSERR_NOERROR:
            raise OSError(f"Cannot open MIDI input (WinMM error {result})")
        winmm.midiInStart(self.handle)

    def close(self):
        if self.handle:
            winmm.midiInStop(self.handle)
            winmm.midiInReset(self.handle)
            winmm.midiInClose(self.handle)
            self.handle = HMIDIIN()
