from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import socket
import threading
from typing import Any, Callable

from aiohttp import WSMsgType, web


SYSTEM_MEDIA_ACTIONS = {
    "system_media.play_pause", "system_media.play", "system_media.pause",
    "system_media.stop", "system_media.next", "system_media.previous",
    "system_media.seek", "system_media.repeat", "system_media.shuffle",
    "system_media.volume", "system_media.mute", "system_media.output",
}

DESKTOP_ACTIONS = {
    "app.stop", "app.blackout", "app.test_lights",
    "global.palette", "global.brightness", "global.custom_color", "macro_control",
    "performance.start",
    "macro.start", "macro.trigger", "macro.save", "macro.clear",
    "video.select", "video.play", "video.pause", "video.previous", "video.next",
    "video.seek", "video.rate", "video.loop", "video.effect", "video.param",
    "music.select", "music.play", "music.pause", "music.previous", "music.next",
    "music.seek", "music.rate", "music.loop", "music.volume", "music.style", "music.param",
    "live.refresh", "live.device", "live.start", "live.stop", "live.style", "live.param",
    "utility.select", "utility.start", "utility.stop", "utility.weather_city",
    "utility.focus_minutes", "utility.focus_pause", "utility.focus_reset",
    "preset.load", "preset.save",
    "device.refresh", "device.connect",
}


class RemoteServer:
    """PIN-authenticated aiohttp server used only on the local network."""

    def __init__(
        self,
        web_root: Path,
        pin: str,
        port: int,
        state_provider: Callable[[], dict[str, Any]],
        command_sink: Callable[[str, Any], None],
        media_bridge=None,
    ):
        self.web_root = Path(web_root)
        self.pin = str(pin)
        self.port = int(port)
        self.state_provider = state_provider
        self.command_sink = command_sink
        self.media_bridge = media_bridge
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_async: asyncio.Event | None = None
        self._clients: set[web.WebSocketResponse] = set()
        self._lock = threading.Lock()
        self._running = False
        self._error = ""

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def configure(self, pin: str | None = None, port: int | None = None):
        if pin is not None:
            self.pin = str(pin)
        if port is not None:
            self.port = int(port)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        with self._lock:
            self._error = ""
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="RemoteServer")
        self._thread.start()

    def stop(self):
        loop = self._loop
        stop_event = self._stop_async
        if loop and stop_event and loop.is_running():
            try:
                loop.call_soon_threadsafe(stop_event.set)
            except RuntimeError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def restart(self, pin: str | None = None, port: int | None = None):
        self.stop()
        self.configure(pin=pin, port=port)
        self.start()

    def _thread_main(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            logging.exception("Remote server failed")
            with self._lock:
                self._running = False
                self._error = str(exc)

    async def _run(self):
        self._loop = asyncio.get_running_loop()
        self._stop_async = asyncio.Event()
        app = web.Application(client_max_size=1024 * 1024)
        app.router.add_get("/", self._index)
        app.router.add_get("/app.js", self._asset)
        app.router.add_get("/style.css", self._asset)
        app.router.add_get("/api/info", self._info)
        app.router.add_get("/api/state", self._state)
        app.router.add_get("/api/lyrics", self._lyrics)
        app.router.add_get("/api/cover/{cover_id}", self._cover)
        app.router.add_get("/ws", self._ws)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            site = web.TCPSite(runner, "0.0.0.0", self.port)
            await site.start()
            with self._lock:
                self._running = True
                self._error = ""
            broadcaster = asyncio.create_task(self._broadcast_loop())
            await self._stop_async.wait()
            broadcaster.cancel()
            try:
                await broadcaster
            except asyncio.CancelledError:
                pass
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
            raise
        finally:
            clients = list(self._clients)
            for ws in clients:
                try:
                    await ws.close(code=1001, message=b"server stopping")
                except Exception:
                    pass
            await runner.cleanup()
            with self._lock:
                self._running = False
                self._clients.clear()
            self._loop = None
            self._stop_async = None

    def _authorized(self, request: web.Request) -> bool:
        token = request.query.get("token", "")
        if not token:
            token = request.headers.get("X-Launchpad-PIN", "")
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        return bool(self.pin) and token == self.pin

    def _require_auth(self, request: web.Request):
        if not self._authorized(request):
            raise web.HTTPUnauthorized(text="Invalid pairing PIN")

    async def _index(self, _request: web.Request):
        return web.FileResponse(self.web_root / "index.html")

    async def _asset(self, request: web.Request):
        # Routes are explicit, so only the basename can ever be requested here.
        # Avoid deriving it from aiohttp's internal route objects; that changed
        # across aiohttp releases and broke Android clients on some builds.
        name = request.path.rsplit("/", 1)[-1]
        if name not in {"app.js", "style.css"}:
            raise web.HTTPNotFound()
        path = self.web_root / name
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    async def _info(self, _request: web.Request):
        return web.json_response({
            "name": "Launchpad Studio Remote",
            "auth": "pin",
            "port": self.port,
            "version": 1,
        })

    def combined_state(self) -> dict[str, Any]:
        try:
            state = dict(self.state_provider() or {})
        except Exception as exc:
            state = {"status": f"state error: {exc}"}
        if self.media_bridge is not None:
            try:
                state["system_media"] = self.media_bridge.snapshot()
            except Exception as exc:
                state["system_media"] = {"available": False, "error": str(exc)}
        state["remote"] = {
            "running": self.running,
            "clients": self.client_count,
            "port": self.port,
        }
        return state

    async def _state(self, request: web.Request):
        self._require_auth(request)
        return web.json_response(self.combined_state())

    async def _lyrics(self, request: web.Request):
        self._require_auth(request)
        if self.media_bridge is None:
            return web.json_response({"key": "", "synced": False, "lines": [], "plain": ""})
        return web.json_response(self.media_bridge.lyrics_payload())

    async def _cover(self, request: web.Request):
        self._require_auth(request)
        if self.media_bridge is None:
            raise web.HTTPNotFound()
        item = self.media_bridge.cover(request.match_info["cover_id"])
        if not item:
            raise web.HTTPNotFound()
        data, content_type = item
        return web.Response(body=data, content_type=content_type)

    async def _ws(self, request: web.Request):
        self._require_auth(request)
        ws = web.WebSocketResponse(heartbeat=20, receive_timeout=None)
        await ws.prepare(request)
        with self._lock:
            self._clients.add(ws)
        try:
            await ws.send_json({"type": "state", "state": self.combined_state()})
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    continue
                try:
                    payload = json.loads(message.data)
                    if payload.get("type") != "command":
                        continue
                    action = str(payload.get("action", ""))
                    value = payload.get("value")
                    if action not in DESKTOP_ACTIONS and action not in SYSTEM_MEDIA_ACTIONS:
                        raise ValueError("Unsupported remote command")
                    if action in SYSTEM_MEDIA_ACTIONS:
                        if self.media_bridge is None:
                            raise RuntimeError("Windows media bridge unavailable")
                        self.media_bridge.command(action.removeprefix("system_media."), value)
                    else:
                        self.command_sink(action, value)
                    await ws.send_json({"type": "ack", "action": action})
                except Exception as exc:
                    await ws.send_json({"type": "error", "error": str(exc)})
        finally:
            with self._lock:
                self._clients.discard(ws)
        return ws

    async def _broadcast_loop(self):
        while True:
            await asyncio.sleep(0.25)
            with self._lock:
                clients = list(self._clients)
            if not clients:
                continue
            message = json.dumps({"type": "state", "state": self.combined_state()}, ensure_ascii=False)
            stale = []
            for ws in clients:
                try:
                    await ws.send_str(message)
                except Exception:
                    stale.append(ws)
            if stale:
                with self._lock:
                    for ws in stale:
                        self._clients.discard(ws)

    @staticmethod
    def lan_ipv4() -> list[str]:
        addresses: set[str] = set()
        try:
            host = socket.gethostname()
            for info in socket.getaddrinfo(host, None, socket.AF_INET):
                ip = info[4][0]
                if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                    addresses.add(ip)
        except OSError:
            pass
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            if ip and not ip.startswith("127."):
                addresses.add(ip)
        except OSError:
            pass
        return sorted(addresses)

    def urls(self) -> list[str]:
        return [f"http://{ip}:{self.port}" for ip in self.lan_ipv4()]
