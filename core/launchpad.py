from __future__ import annotations

import colorsys
import threading
from dataclasses import dataclass

from .midi_winmm import MidiIn, MidiOut, input_devices, output_devices


def pad_id(x: int, y: int) -> int | None:
    """Historical MK2 address helper kept for settings-file compatibility."""
    if y == 0 and 0 <= x <= 7:
        return 104 + x
    if 1 <= y <= 8 and 0 <= x <= 8:
        return (9 - y) * 10 + 1 + x
    return None


def _modern_id(x: int, y: int) -> int | None:
    if y == 0 and 0 <= x <= 7:
        return 91 + x
    if 1 <= y <= 8:
        if x == -1:
            return (9 - y) * 10
        if 0 <= x <= 8:
            return (9 - y) * 10 + 1 + x
    if y == 9 and 0 <= x <= 7:
        return 1 + x
    return None


def _legacy_id(x: int, y: int) -> int | None:
    if y == 0 and 0 <= x <= 7:
        return 104 + x
    if 1 <= y <= 8 and 0 <= x <= 8:
        return (8 - y) * 16 + x
    return None


CANONICAL_PADS = tuple((x, y) for y in range(9) for x in range(9) if pad_id(x, y) is not None)
ALL_PADS = list(CANONICAL_PADS)
PRO_PADS = tuple([(x, 0) for x in range(8)] +
                 [(x, y) for y in range(1, 9) for x in range(-1, 9)] +
                 [(x, 9) for x in range(8)])


@dataclass(frozen=True)
class LaunchpadModel:
    key: str
    name: str
    aliases: tuple[str, ...]
    pads: tuple[tuple[int, int], ...]
    address_kind: str
    protocol: str
    product_id: int | None = None

    def address(self, x: int, y: int) -> int | None:
        if self.address_kind == "modern":
            return _modern_id(x, y)
        if self.address_kind == "legacy":
            return _legacy_id(x, y)
        return pad_id(x, y)


MODELS = (
    LaunchpadModel("pro_mk3", "Launchpad Pro MK3", ("launchpad pro mk3", "launchpad pro [mk3]"), PRO_PADS, "modern", "modern_rgb", 0x0E),
    LaunchpadModel("mini_mk3", "Launchpad Mini MK3", ("launchpad mini mk3", "launchpad mini [mk3]"), tuple(CANONICAL_PADS), "modern", "modern_rgb", 0x0D),
    LaunchpadModel("x", "Launchpad X", ("launchpad x",), tuple(CANONICAL_PADS), "modern", "modern_rgb", 0x0C),
    LaunchpadModel("pro", "Launchpad Pro", ("launchpad pro",), PRO_PADS, "modern", "mk2_rgb", 0x10),
    LaunchpadModel("mk2", "Launchpad MK2", ("launchpad mk2", "launchpad [mk2]"), tuple(CANONICAL_PADS), "mk2", "mk2_rgb", 0x18),
    LaunchpadModel("mini_mk2", "Launchpad Mini MK2", ("launchpad mini mk2", "launchpad mini [mk2]"), tuple(CANONICAL_PADS), "legacy", "legacy_palette"),
    LaunchpadModel("mini", "Launchpad Mini", ("launchpad mini",), tuple(CANONICAL_PADS), "legacy", "legacy_palette"),
    LaunchpadModel("s", "Launchpad S", ("launchpad s",), tuple(CANONICAL_PADS), "legacy", "legacy_palette"),
    LaunchpadModel("original", "Launchpad (Original)", ("launchpad",), tuple(CANONICAL_PADS), "legacy", "legacy_palette"),
)
MODEL_BY_KEY = {model.key: model for model in MODELS}


def detect_model(*names: str, preferred: str = "auto") -> LaunchpadModel:
    if preferred in MODEL_BY_KEY:
        return MODEL_BY_KEY[preferred]
    joined = " ".join(names).casefold()
    for model in MODELS:  # Specific aliases precede generic ones.
        if any(alias in joined for alias in model.aliases):
            return model
    return MODEL_BY_KEY["mk2"]


class LaunchpadDevice:
    def __init__(self, on_press=None, model="mk2"):
        self.out = MidiOut()
        self.ins = MidiIn(self._midi_event)
        self.on_press = on_press
        self.connected = False
        self.model = MODEL_BY_KEY.get(model, MODEL_BY_KEY["mk2"])
        self.colors = {xy: (0, 0, 0) for xy in self.model.pads}
        self._last = dict(self.colors)
        self._send_lock = threading.Lock()

    @staticmethod
    def devices():
        return input_devices(), output_devices()

    @property
    def pads(self):
        return self.model.pads

    def set_model(self, key="auto", *device_names):
        self.model = detect_model(*device_names, preferred=key)
        self.colors = {xy: (0, 0, 0) for xy in self.model.pads}
        self._last = dict(self.colors)
        return self.model

    def pad_id(self, x, y):
        return self.model.address(x, y)

    def pad_label(self, x, y):
        number = self.pad_id(x, y)
        return "—" if number is None else str(number)

    def macro_key(self, x, y):
        return f"{self.model.key}:{self.pad_id(x, y)}"

    def connect(self, in_index: int, out_index: int, model="auto"):
        ins, outs = self.devices()
        in_name = ins[in_index] if 0 <= in_index < len(ins) else ""
        out_name = outs[out_index] if 0 <= out_index < len(outs) else ""
        self.disconnect(clear=False)
        self.set_model(model, in_name, out_name)
        self.out.open(out_index)
        try:
            self.ins.open(in_index)
            self.connected = True
            self._enter_programmer_mode()
            self.clear(force=True)
        except Exception:
            self.out.close(); self.connected = False
            raise

    def _enter_programmer_mode(self):
        if self.model.protocol == "modern_rgb":
            self.out.sysex(bytes([0xF0, 0, 0x20, 0x29, 2, self.model.product_id, 0x0E, 1, 0xF7]))
        elif self.model.protocol == "legacy_palette":
            # Classic Launchpad drum-rack mapping exposes the full 8x8 surface.
            self.out.short(0xB0, 0, 1)

    def disconnect(self, clear=True):
        if clear and self.connected:
            try:
                self.clear(force=True)
                if self.model.protocol == "modern_rgb":
                    self.out.sysex(bytes([0xF0, 0, 0x20, 0x29, 2, self.model.product_id, 0x0E, 0, 0xF7]))
                elif self.model.protocol == "legacy_palette":
                    self.out.short(0xB0, 0, 0)
            except Exception:
                pass
        self.ins.close(); self.out.close(); self.connected = False

    def _xy_from_event(self, status, number):
        kind = status & 0xF0
        for xy in self.model.pads:
            if self.model.address(*xy) != number:
                continue
            if self.model.address_kind == "legacy" and xy[1] == 0 and kind != 0xB0:
                continue
            return xy
        return None

    def _midi_event(self, status, number, value):
        xy = self._xy_from_event(status, number)
        if xy and self.on_press:
            self.on_press(xy[0], xy[1], value > 0 and (status & 0xF0) != 0x80, value)

    @staticmethod
    def _rgb(rgb):
        return tuple(max(0, min(255, int(v))) for v in rgb)

    def _send_changes(self, changes):
        model = self.model
        if model.protocol == "modern_rgb":
            # Official modern-device messages allow at most 81 colour specs.
            # Chunks of 80 also keep WinMM buffers comfortably small.
            for start in range(0,len(changes),80):
                payload = bytearray([0xF0, 0, 0x20, 0x29, 2, model.product_id, 0x03])
                for number, _xy, rgb in changes[start:start+80]:
                    payload.extend([3, number, *(round(v * 127 / 255) for v in rgb)])
                payload.append(0xF7); self.out.sysex(bytes(payload))
        elif model.protocol == "mk2_rgb":
            for start in range(0,len(changes),80):
                payload = bytearray([0xF0, 0, 0x20, 0x29, 2, model.product_id, 0x0B])
                for number, _xy, rgb in changes[start:start+80]:
                    payload.extend([number, *(round(v * 63 / 255) for v in rgb)])
                payload.append(0xF7); self.out.sysex(bytes(payload))
        else:
            for number, xy, rgb in changes:
                r = round(max(rgb[0], rgb[2] * .45) * 3 / 255)
                g = round(max(rgb[1], rgb[2] * .75) * 3 / 255)
                self.out.short(0xB0 if xy[1] == 0 else 0x90, number, r + 16 * g)

    def set_frame(self, colors, force=False):
        normalized, changes = {}, []
        for xy in self.model.pads:
            rgb = self._rgb(colors.get(xy, (0, 0, 0)))
            normalized[xy] = rgb
            if force or rgb != self._last.get(xy):
                changes.append((self.model.address(*xy), xy, rgb))
        self.colors = normalized
        if self.connected and changes:
            with self._send_lock:
                self._send_changes(changes)
        self._last = dict(normalized)

    def clear(self, force=False):
        self.set_frame({xy: (0, 0, 0) for xy in self.model.pads}, force=force)

    def test_pattern(self):
        frame = {}
        min_x = min(x for x, _ in self.model.pads)
        for x, y in self.model.pads:
            hue = (((x - min_x) / 10) + (y / 18)) % 1.0
            frame[(x, y)] = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(hue, .9, .85))
        self.set_frame(frame, force=True)


LaunchpadMK2 = LaunchpadDevice
