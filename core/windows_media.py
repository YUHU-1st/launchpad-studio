from __future__ import annotations

import asyncio
import bisect
import hashlib
import json
import logging
import os
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


_LRC_LINE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\](.*)")


def parse_lrc(text: str) -> list[dict[str, Any]]:
    """Parse synchronized LRC into monotonically ordered timestamped lines."""
    lines: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        matches = list(_LRC_LINE.finditer(raw))
        if not matches:
            continue
        lyric = matches[-1].group(4).strip()
        for match in matches:
            fraction = match.group(3) or "0"
            seconds = int(match.group(1)) * 60 + int(match.group(2))
            seconds += int(fraction) / (10 ** len(fraction))
            lines.append({"time": round(seconds, 3), "text": lyric})
    lines.sort(key=lambda item: item["time"])
    return lines


class WindowsAudioSystem:
    """Small wrapper around Windows Core Audio through pycaw."""

    @staticmethod
    def snapshot() -> dict[str, Any]:
        try:
            from pycaw.constants import AudioDeviceState
            from pycaw.pycaw import AudioUtilities

            current = AudioUtilities.GetSpeakers()
            volume = current.EndpointVolume
            outputs = []
            for device in AudioUtilities.GetAllDevices():
                if getattr(device, "state", None) != AudioDeviceState.Active:
                    continue
                try:
                    if AudioUtilities.GetEndpointDataFlow(device.id) != "eRender":
                        continue
                except Exception:
                    continue
                outputs.append({
                    "id": device.id,
                    "name": device.FriendlyName,
                    "active": device.id == current.id,
                })
            outputs.sort(key=lambda item: (not item["active"], item["name"].casefold()))
            return {
                "available": True,
                "volume": round(float(volume.GetMasterVolumeLevelScalar()) * 100, 1),
                "mute": bool(volume.GetMute()),
                "active_output": current.id,
                "outputs": outputs,
            }
        except Exception as exc:
            return {
                "available": False,
                "volume": 0.0,
                "mute": False,
                "active_output": "",
                "outputs": [],
                "error": str(exc),
            }

    @staticmethod
    def set_volume(percent: float):
        from pycaw.pycaw import AudioUtilities

        level = max(0.0, min(100.0, float(percent))) / 100.0
        AudioUtilities.GetSpeakers().EndpointVolume.SetMasterVolumeLevelScalar(level, None)

    @staticmethod
    def set_mute(muted: bool):
        from pycaw.pycaw import AudioUtilities

        AudioUtilities.GetSpeakers().EndpointVolume.SetMute(bool(muted), None)

    @staticmethod
    def set_default_output(device_id: str):
        from pycaw.constants import ERole
        from pycaw.pycaw import AudioUtilities

        AudioUtilities.SetDefaultDevice(
            device_id,
            [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications],
        )


class SystemMediaBridge:
    """Mirror Windows GSMTC state and accept remote control commands."""

    def __init__(self):
        self._stop = threading.Event()
        self._commands: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._state_lock = threading.Lock()
        self._state: dict[str, Any] = self._empty_state()
        self._covers_lock = threading.Lock()
        self._covers: dict[str, tuple[bytes, str]] = {}
        self._lyrics: list[dict[str, Any]] = []
        self._plain_lyrics = ""
        self._lyrics_key = ""
        self._thread: threading.Thread | None = None

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "available": False,
            "app": "",
            "title": "",
            "artist": "",
            "album": "",
            "subtitle": "",
            "playing": False,
            "status": "closed",
            "position": 0.0,
            "duration": 0.0,
            "sampled_at": time.time(),
            "can_seek": False,
            "repeat": "none",
            "shuffle": False,
            "cover_id": "",
            "lyrics_key": "",
            "lyric_line": "",
            "lyric_next": "",
            "lyrics_available": False,
            "controls": {},
            "audio": WindowsAudioSystem.snapshot(),
            "last_command": {},
        }

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="SystemMediaBridge")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def command(self, action: str, value: Any = None):
        self._commands.put((action, value))

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            state = json.loads(json.dumps(self._state, ensure_ascii=False))
        position = float(state.get("position") or 0.0)
        if state.get("playing"):
            position += max(0.0, time.time() - float(state.get("sampled_at") or time.time()))
            duration = float(state.get("duration") or 0.0)
            if duration:
                position = min(position, duration)
        state["position"] = round(position, 3)
        self._apply_lyric_line(state, position)
        return state

    def lyrics_payload(self) -> dict[str, Any]:
        with self._state_lock:
            key = self._state.get("lyrics_key", "")
        return {
            "key": key,
            "synced": bool(self._lyrics),
            "lines": list(self._lyrics),
            "plain": self._plain_lyrics,
        }

    def cover(self, cover_id: str) -> tuple[bytes, str] | None:
        with self._covers_lock:
            return self._covers.get(cover_id)

    def _thread_main(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            logging.exception("System media bridge failed")
            with self._state_lock:
                self._state.update(available=False, error=str(exc))

    async def _run(self):
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
            manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        except Exception as exc:
            manager = None
            with self._state_lock:
                self._state.update(available=False, error=f"Windows Media Control unavailable: {exc}")

        last_audio = 0.0
        last_metadata = 0.0
        cached_media: dict[str, Any] = {}
        session_key = ""
        while not self._stop.is_set():
            session = manager.get_current_session() if manager else None
            await self._drain_commands(session)
            now = time.monotonic()
            if session:
                current_key = session.source_app_user_model_id or "unknown"
                if current_key != session_key:
                    session_key = current_key
                    cached_media = {}
                    last_metadata = 0.0
                if now - last_metadata >= 0.8:
                    cached_media = await self._read_media_properties(session, cached_media)
                    last_metadata = now
                state = self._read_playback_state(session, cached_media)
            else:
                state = self._empty_state()
                with self._state_lock:
                    state["audio"] = self._state.get("audio", state["audio"])
                    state["last_command"] = self._state.get("last_command", {})
                session_key = ""
                cached_media = {}
            if now - last_audio >= 0.8:
                state["audio"] = WindowsAudioSystem.snapshot()
                last_audio = now
            else:
                with self._state_lock:
                    state["audio"] = self._state.get("audio", state.get("audio", {}))
            with self._state_lock:
                state["last_command"] = self._state.get("last_command", {})
                self._state.update(state)
            await asyncio.sleep(0.2)

    async def _read_media_properties(self, session, previous: dict[str, Any]) -> dict[str, Any]:
        try:
            props = await session.try_get_media_properties_async()
            if not props:
                return previous
            media = {
                "title": props.title or "",
                "artist": props.artist or props.album_artist or "",
                "album": props.album_title or "",
                "subtitle": props.subtitle or "",
                "cover_id": previous.get("cover_id", ""),
            }
            key = "\x1f".join((media["title"], media["artist"], media["album"]))
            if key and key != previous.get("track_key"):
                media["track_key"] = key
                self._lyrics = []
                self._plain_lyrics = ""
                self._lyrics_key = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:16]
                asyncio.create_task(self._resolve_lyrics(media["title"], media["artist"], media["album"], self._lyrics_key))
                try:
                    cover = await self._read_thumbnail(props.thumbnail)
                    if cover:
                        digest = hashlib.sha1(cover[0]).hexdigest()[:20]
                        with self._covers_lock:
                            self._covers = {digest: cover}
                        media["cover_id"] = digest
                    else:
                        media["cover_id"] = ""
                except Exception:
                    media["cover_id"] = ""
            else:
                media["track_key"] = previous.get("track_key", key)
            return media
        except Exception:
            return previous

    @staticmethod
    async def _read_thumbnail(reference) -> tuple[bytes, str] | None:
        if not reference:
            return None
        from winrt.windows.storage.streams import Buffer, InputStreamOptions

        stream = await reference.open_read_async()
        size = min(int(stream.size), 4 * 1024 * 1024)
        if size <= 0:
            return None
        buffer = Buffer(size)
        result = await stream.read_async(buffer, size, InputStreamOptions.NONE)
        data = bytes(memoryview(result))
        content_type = getattr(stream, "content_type", "") or "image/jpeg"
        try:
            stream.close()
        except Exception:
            pass
        return data, content_type

    def _read_playback_state(self, session, media: dict[str, Any]) -> dict[str, Any]:
        try:
            playback = session.get_playback_info()
            timeline = session.get_timeline_properties()
            controls = playback.controls
            start = max(0.0, timeline.start_time.total_seconds())
            end = max(start, timeline.end_time.total_seconds())
            position = max(0.0, timeline.position.total_seconds() - start)
            duration = max(0.0, end - start)
            repeat_value = playback.auto_repeat_mode
            repeat = {0: "none", 1: "track", 2: "list"}.get(int(repeat_value) if repeat_value is not None else 0, "none")
            status = playback.playback_status
            status_int = int(status)
            status_name = {0: "closed", 1: "opened", 2: "changing", 3: "stopped", 4: "playing", 5: "paused"}.get(status_int, "unknown")
            state = {
                "available": True,
                "app": session.source_app_user_model_id or "",
                **media,
                "playing": status_int == 4,
                "status": status_name,
                "position": round(position, 3),
                "duration": round(duration, 3),
                "sampled_at": time.time(),
                "can_seek": bool(controls.is_playback_position_enabled) and duration > 0,
                "repeat": repeat,
                "shuffle": bool(playback.is_shuffle_active) if playback.is_shuffle_active is not None else False,
                "lyrics_key": self._lyrics_key,
                "lyrics_available": bool(self._lyrics or self._plain_lyrics),
                "controls": {
                    "play": bool(controls.is_play_enabled),
                    "pause": bool(controls.is_pause_enabled),
                    "toggle": bool(controls.is_play_pause_toggle_enabled),
                    "next": bool(controls.is_next_enabled),
                    "previous": bool(controls.is_previous_enabled),
                    "stop": bool(controls.is_stop_enabled),
                    "seek": bool(controls.is_playback_position_enabled) and duration > 0,
                    "repeat": bool(controls.is_repeat_enabled),
                    "shuffle": bool(controls.is_shuffle_enabled),
                },
            }
            self._apply_lyric_line(state, position)
            return state
        except Exception as exc:
            return {
                "available": True,
                "app": session.source_app_user_model_id or "",
                **media,
                "playing": False,
                "status": "unknown",
                "position": 0.0,
                "duration": 0.0,
                "sampled_at": time.time(),
                "can_seek": False,
                "repeat": "none",
                "shuffle": False,
                "lyrics_key": self._lyrics_key,
                "lyrics_available": bool(self._lyrics or self._plain_lyrics),
                "controls": {},
                "error": str(exc),
            }

    def _apply_lyric_line(self, state: dict[str, Any], position: float):
        if not self._lyrics:
            state["lyric_line"] = self._plain_lyrics.splitlines()[0] if self._plain_lyrics else ""
            state["lyric_next"] = ""
            return
        times = [item["time"] for item in self._lyrics]
        index = bisect.bisect_right(times, position) - 1
        if index < 0:
            state["lyric_line"] = ""
            state["lyric_next"] = self._lyrics[0]["text"] if self._lyrics else ""
            return
        state["lyric_line"] = self._lyrics[index]["text"]
        state["lyric_next"] = self._lyrics[index + 1]["text"] if index + 1 < len(self._lyrics) else ""

    async def _resolve_lyrics(self, title: str, artist: str, album: str, expected_key: str):
        if not title:
            return
        result = await asyncio.to_thread(self._fetch_lyrics, title, artist, album)
        if expected_key != self._lyrics_key:
            return
        self._lyrics = parse_lrc(result.get("syncedLyrics", ""))
        self._plain_lyrics = result.get("plainLyrics", "") or ""
        with self._state_lock:
            self._state["lyrics_available"] = bool(self._lyrics or self._plain_lyrics)

    @staticmethod
    def _fetch_lyrics(title: str, artist: str, album: str) -> dict[str, Any]:
        params = {"track_name": title}
        if artist:
            params["artist_name"] = artist
        if album:
            params["album_name"] = album
        url = "https://lrclib.net/api/search?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "LaunchpadStudio/1.1"})
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            if isinstance(payload, list) and payload:
                for candidate in payload:
                    if candidate.get("syncedLyrics"):
                        return candidate
                return payload[0]
        except (OSError, ValueError, urllib.error.URLError):
            pass
        return {}

    @staticmethod
    def _playing(session) -> bool | None:
        try:
            return int(session.get_playback_info().playback_status) == 4
        except Exception:
            return None

    async def _drain_commands(self, session):
        while True:
            try:
                action, value = self._commands.get_nowait()
            except queue.Empty:
                return
            ok = False
            fallback = False
            error = ""
            try:
                if action == "volume":
                    WindowsAudioSystem.set_volume(float(value)); ok = True
                elif action == "mute":
                    WindowsAudioSystem.set_mute(bool(value)); ok = True
                elif action == "output":
                    WindowsAudioSystem.set_default_output(str(value)); ok = True
                else:
                    ok, fallback = await self._media_command_with_fallback(session, action, value)
            except Exception as exc:
                error = str(exc)
                if action in {"play_pause", "play", "pause", "next", "previous", "stop"}:
                    fallback = self._fallback_media_key(action, self._playing(session) if session else None)
                    ok = ok or fallback
                logging.debug("System media command failed: %s", action, exc_info=True)
            with self._state_lock:
                self._state["last_command"] = {
                    "action": action,
                    "ok": bool(ok),
                    "fallback": bool(fallback),
                    "error": error,
                    "at": time.time(),
                }

    async def _media_command_with_fallback(self, session, action: str, value: Any) -> tuple[bool, bool]:
        if not session:
            fallback = self._fallback_media_key(action, None)
            return fallback, fallback

        before = self._playing(session)
        ok = await self._media_command(session, action, value)
        fallback = False

        # Some players (notably some NetEase builds) return success from GSMTC
        # but ignore the play-state change. Confirm it before deciding whether to
        # emit one media-key toggle. Never double-send skip commands on a merely
        # slow metadata update.
        if action in {"play_pause", "play", "pause"}:
            await asyncio.sleep(0.32)
            after = self._playing(session)
            if action == "play_pause":
                changed = before is None or after is None or after != before
                needs_fallback = not ok or not changed
            elif action == "play":
                needs_fallback = after is not True
            else:
                needs_fallback = after is not False
            if needs_fallback:
                fallback = self._fallback_media_key(action, after)
                ok = ok or fallback
        elif action in {"next", "previous", "stop"} and not ok:
            fallback = self._fallback_media_key(action, before)
            ok = ok or fallback
        return bool(ok), bool(fallback)

    @staticmethod
    async def _media_command(session, action: str, value: Any) -> bool:
        if not session:
            return False
        if action == "play_pause":
            return bool(await session.try_toggle_play_pause_async())
        if action == "play":
            if SystemMediaBridge._playing(session) is True:
                return True
            return bool(await session.try_play_async())
        if action == "pause":
            if SystemMediaBridge._playing(session) is False:
                return True
            return bool(await session.try_pause_async())
        if action == "stop":
            return bool(await session.try_stop_async())
        if action == "next":
            return bool(await session.try_skip_next_async())
        if action == "previous":
            return bool(await session.try_skip_previous_async())
        if action == "seek":
            try:
                controls = session.get_playback_info().controls
                if not controls.is_playback_position_enabled:
                    return False
            except Exception:
                return False
            seconds = max(0.0, float(value))
            return bool(await session.try_change_playback_position_async(int(seconds * 10_000_000)))
        if action == "repeat":
            from winrt.windows.media import MediaPlaybackAutoRepeatMode
            mode = {
                "none": MediaPlaybackAutoRepeatMode.NONE,
                "track": MediaPlaybackAutoRepeatMode.TRACK,
                "list": MediaPlaybackAutoRepeatMode.LIST,
            }.get(str(value), MediaPlaybackAutoRepeatMode.NONE)
            return bool(await session.try_change_auto_repeat_mode_async(mode))
        if action == "shuffle":
            return bool(await session.try_change_shuffle_active_async(bool(value)))
        return False

    @staticmethod
    def _fallback_media_key(action: str, playing: bool | None) -> bool:
        if os.name != "nt":
            return False
        # Windows has one play/pause toggle media key, not distinct play/pause
        # keys. Only send the toggle when it moves toward the requested state.
        if action == "play" and playing is True:
            return True
        if action == "pause" and playing is False:
            return True
        keys = {
            "play_pause": 0xB3,
            "play": 0xB3,
            "pause": 0xB3,
            "next": 0xB0,
            "previous": 0xB1,
            "stop": 0xB2,
        }
        vk = keys.get(action)
        if vk is None:
            return False
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 0x0002, 0)
            return True
        except Exception:
            return False
