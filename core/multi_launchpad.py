from __future__ import annotations

from typing import Iterable


LINK_EXTEND = "扩展画布"
LINK_MIRROR = "复制画面"
LINK_INDEPENDENT = "独立模式"
LINK_MODES = (LINK_EXTEND, LINK_MIRROR, LINK_INDEPENDENT)

MODE_SOURCES = ("性能监控", "宏按键", "视频播放", "音乐演示", "实时拾音", "工具与游戏")


_DIGITS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
}


def normalize_configs(raw_devices, input_names, output_names, model_keys, link_mode):
    if link_mode not in LINK_MODES:
        raise ValueError("不支持的联动方式")
    if not isinstance(raw_devices, list) or not 1 <= len(raw_devices) <= 16:
        raise ValueError("请配置 1 至 16 台设备")
    configs = []
    for index, raw in enumerate(raw_devices):
        if not isinstance(raw, dict):
            raise ValueError("设备参数错误")
        device_id = str(raw.get("id") or f"lp{index + 1}")
        if not device_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("设备 ID 无效")
        number = int(raw.get("number", index + 1))
        x, y = int(raw.get("x", index)), int(raw.get("y", 0))
        mode, model = str(raw.get("mode", "性能监控")), str(raw.get("model", "auto"))
        input_index, output_index = int(raw.get("input_index", -1)), int(raw.get("output_index", -1))
        if not 1 <= number <= 99 or not -8 <= x <= 8 or not -8 <= y <= 8:
            raise ValueError("编号或坐标超出范围")
        if mode not in MODE_SOURCES or model not in model_keys:
            raise ValueError("设备模式或型号无效")
        if not 0 <= input_index < len(input_names) or not 0 <= output_index < len(output_names):
            raise ValueError("MIDI 端口不存在")
        configs.append({"id": device_id, "number": number, "x": x, "y": y, "mode": mode, "model": model,
                        "input": input_names[input_index], "output": output_names[output_index],
                        "input_index": input_index, "output_index": output_index})
    if len({item["id"] for item in configs}) != len(configs):
        raise ValueError("设备 ID 重复")
    if len({item["number"] for item in configs}) != len(configs):
        raise ValueError("设备编号重复")
    if len({item["input_index"] for item in configs}) != len(configs) or len({item["output_index"] for item in configs}) != len(configs):
        raise ValueError("MIDI 端口重复")
    if link_mode == LINK_EXTEND and len({(item["x"], item["y"]) for item in configs}) != len(configs):
        raise ValueError("扩展画布位置重叠")
    return configs


def canvas_geometry(configs: Iterable[dict]) -> tuple[int, int, dict[str, tuple[int, int]]]:
    """Return tile width/height and zero-based tile positions for a saved layout."""
    items = list(configs)
    if not items:
        return 1, 1, {}
    min_x = min(int(item.get("x", 0)) for item in items)
    min_y = min(int(item.get("y", 0)) for item in items)
    positions = {
        str(item["id"]): (int(item.get("x", 0)) - min_x, int(item.get("y", 0)) - min_y)
        for item in items
    }
    return (
        max(x for x, _ in positions.values()) + 1,
        max(y for _, y in positions.values()) + 1,
        positions,
    )


def frame_size(frame: dict[tuple[int, int], tuple[int, int, int]]) -> tuple[int, int]:
    top = [x for x, y in frame if y == 0 and x >= 0]
    width = max(top) + 1 if top else max((x for x, y in frame if x >= 0 and y > 0), default=7) + 1
    rows = [y for x, y in frame if 0 <= x < width and y > 0]
    return max(1, width), max(1, max(rows, default=8))


def _sample(frame, x, y, source_width, source_height, target_width, target_height):
    sx = min(source_width - 1, int(x * source_width / max(1, target_width)))
    sy = min(source_height - 1, int(y * source_height / max(1, target_height)))
    return frame.get((sx, sy + 1), (0, 0, 0))


def device_frame(
    frame: dict[tuple[int, int], tuple[int, int, int]],
    pads: Iterable[tuple[int, int]],
    tile: tuple[int, int] = (0, 0),
    canvas_tiles: tuple[int, int] = (1, 1),
    extend: bool = False,
) -> dict[tuple[int, int], tuple[int, int, int]]:
    """Fit or crop a logical frame to one Launchpad, including its control LEDs."""
    source_width, source_height = frame_size(frame)
    tiles_w, tiles_h = canvas_tiles
    target_width, target_height = (tiles_w * 8, tiles_h * 8) if extend else (8, 8)
    offset_x, offset_y = (tile[0] * 8, tile[1] * 8) if extend else (0, 0)
    core = {}
    for y in range(8):
        for x in range(8):
            core[(x, y + 1)] = _sample(
                frame, offset_x + x, offset_y + y,
                source_width, source_height, target_width, target_height,
            )
    result = {}
    for x, y in pads:
        if 0 <= x < 8 and 1 <= y <= 8:
            color = core[(x, y)]
        elif y == 0 and 0 <= x < 8:
            global_x = offset_x + x
            source_x = min(source_width - 1, int(global_x * source_width / max(1, target_width)))
            color = frame.get((source_x, 0), core[(x, 1)])
        elif x == 8 and 1 <= y <= 8:
            global_y = offset_y + y - 1
            source_y = min(source_height - 1, int(global_y * source_height / max(1, target_height))) + 1
            color = frame.get((source_width, source_y), core[(7, y)])
        elif x == -1 and 1 <= y <= 8:
            color = core[(0, y)]
        elif y == 9 and 0 <= x < 8:
            color = core[(x, 8)]
        else:
            color = (0, 0, 0)
        result[(x, y)] = color
    return result


def route_frames(
    configs: Iterable[dict],
    pads_by_id: dict[str, Iterable[tuple[int, int]]],
    frames: dict[str, dict[tuple[int, int], tuple[int, int, int]]],
    link_mode: str,
    active_source: str | None,
) -> dict[str, dict[tuple[int, int], tuple[int, int, int]]]:
    items = list(configs)
    width, height, positions = canvas_geometry(items)
    routed = {}
    for item in items:
        device_id = str(item["id"])
        pads = pads_by_id.get(device_id)
        if not pads:
            continue
        source = str(item.get("mode") or active_source or "") if link_mode == LINK_INDEPENDENT else str(active_source or "")
        frame = frames.get(source)
        if frame is None:
            continue
        routed[device_id] = device_frame(
            frame,
            pads,
            positions.get(device_id, (0, 0)),
            (width, height),
            extend=link_mode == LINK_EXTEND,
        )
    return routed


def number_frame(number: int, color=(0, 210, 255), dim=(0, 28, 38)):
    """Draw a centered one/two-digit identifier on an 8x8 Launchpad core."""
    text = str(max(1, min(99, int(number))))
    width = len(text) * 4 - 1
    start_x = (8 - width) // 2
    start_y = 2
    frame = {(x, y): dim for y in range(1, 9) for x in range(8)}
    for index, digit in enumerate(text):
        for row, bits in enumerate(_DIGITS[digit]):
            for column, bit in enumerate(bits):
                if bit == "1":
                    frame[(start_x + index * 4 + column, start_y + row)] = color
    for x in range(8):
        frame[(x, 0)] = color if x < len(text) else dim
    for y in range(1, 9):
        frame[(8, y)] = color if y <= len(text) else dim
    return frame
