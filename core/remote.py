from __future__ import annotations

import asyncio
import json
import socket
import threading
from pathlib import Path
from typing import Any, Callable


class RemoteServer:
    """LAN-only HTTP/WebSocket bridge used by the Android remote."""

    def __init__(
        self,
        web_root: Path,
        token: str,
        port: int,
        on_command: Callable[[str, Any], None],
        media_bridge,
    ):
        self.web_root = Path(web_root)
        self.token = str(token)
        self.port = int(port)
        self.on_command = on_command
        self.media_bridge = media_bridge
        self._state_lock = threading.Lock()
        self._app_state: dict[str, Any] = {}
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner = None
        self._clients: set[Any] = set()
        self._started = threading.Event()
        self._stopped = threading.Event()
        self.error = ""

    @property
    def connected_clients(self) -> int:
        return len(self._clients)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self.error = ""
        self._started.clear()
        self._stopped.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="LaunchpadRemoteServer")
        self._thread.start()
        self._started.wait(timeout=3.0)

    def stop(self):
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self._shutdown()))
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def update_app_state(self, state: dict[str, Any]):
        with self._state_lock:
            self._app_state = state

    def state(self) -> dict[str, Any]:
        with self._state_lock:
            app_state = json.loads(json.dumps(self._app_state, ensure_ascii=False))
        app_state["system_media"] = self.media_bridge.snapshot()
        app_state["remote_clients"] = self.connected_clients
        return app_state

    def urls(self) -> list[str]:
        return [f"http://{address}:{self.port}/" for address in self.local_addresses()]

    @staticmethod
    def local_addresses() -> list[str]:
        candidates: set[str] = set()
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                candidates.add(info[4][0])
        except OSError:
            pass
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("8.8.8.8", 80))
            candidates.add(probe.getsockname()[0])
            probe.close()
        except OSError:
            pass
        usable = [ip for ip in candidates if not ip.startswith("127.") and not ip.startswith("169.254.")]
        return sorted(usable) or ["127.0.0.1"]

    def _thread_main(self):
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self.error = str(exc)
            self._started.set()
            self._stopped.set()

    async def _serve(self):
        from aiohttp import web

        self._loop = asyncio.get_running_loop()
        app = web.Application()
        app.router.add_get("/", self._index)
        app.router.add_get("/app.js", self._asset)
        app.router.add_get("/style.css", self._asset)
        app.router.add_get("/api/info", self._info)
        app.router.add_get("/api/state", self._state_endpoint)
        app.router.add_get("/api/lyrics", self._lyrics)
        app.router.add_get("/api/cover/{cover_id}", self._cover)
        app.router.add_get("/ws", self._websocket)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        self._started.set()
        broadcaster = asyncio.create_task(self._broadcast_loop())
        try:
            await self._stopped_async()
        finally:
            broadcaster.cancel()
            await asyncio.gather(broadcaster, return_exceptions=True)
            await self._runner.cleanup()
            self._runner = None
            self._loop = None
            self._stopped.set()

    async def _stopped_async(self):
        while not self._stopped.is_set():
            await asyncio.sleep(0.2)

    async def _shutdown(self):
        self._stopped.set()
        for ws in list(self._clients):
            try:
                await ws.close(code=1001, message=b"server stopping")
            except Exception:
                pass

    async def _index(self, request):
        from aiohttp import web

        return web.FileResponse(self.web_root / "index.html")

    async def _asset(self, request):
        from aiohttp import web

        name = request.path.rsplit("/", 1)[-1]
        return web.FileResponse(self.web_root / name)

    async def _info(self, request):
        from aiohttp import web

        return web.json_response({
            "name": "Launchpad Studio Remote",
            "auth": "pin",
            "port": self.port,
        })

    def _authorized(self, request) -> bool:
        supplied = request.query.get("token", "") or request.headers.get("X-Launchpad-Token", "")
        return bool(self.token) and supplied == self.token

    async def _state_endpoint(self, request):
        from aiohttp import web

        if not self._authorized(request):
            raise web.HTTPUnauthorized(text="Invalid pairing PIN")
        return web.json_response(self.state(), dumps=lambda value: json.dumps(value, ensure_ascii=False))

    async def _lyrics(self, request):
        from aiohttp import web

        if not self._authorized(request):
            raise web.HTTPUnauthorized(text="Invalid pairing PIN")
        return web.json_response(self.media_bridge.lyrics_payload(), dumps=lambda value: json.dumps(value, ensure_ascii=False))

    async def _cover(self, request):
        from aiohttp import web

        if not self._authorized(request):
            raise web.HTTPUnauthorized(text="Invalid pairing PIN")
        cover = self.media_bridge.cover(request.match_info["cover_id"])
        if not cover:
            raise web.HTTPNotFound()
        data, content_type = cover
        return web.Response(body=data, content_type=content_type)

    async def _websocket(self, request):
        from aiohttp import WSMsgType, web

        if not self._authorized(request):
            raise web.HTTPUnauthorized(text="Invalid pairing PIN")
        ws = web.WebSocketResponse(heartbeat=20, receive_timeout=60)
        await ws.prepare(request)
        self._clients.add(ws)
        await ws.send_json({"type": "hello", "state": self.state()}, dumps=lambda value: json.dumps(value, ensure_ascii=False))
        try:
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    await self._handle_message(ws, message.data)
                elif message.type in (WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSED):
                    break
        finally:
            self._clients.discard(ws)
        return ws

    async def _handle_message(self, ws, raw: str):
        try:
            payload = json.loads(raw)
        except ValueError:
            return
        if payload.get("type") == "ping":
            await ws.send_json({"type": "pong"})
            return
        if payload.get("type") != "command":
            return
        action = str(payload.get("action", ""))
        value = payload.get("value")
        if action.startswith("system_media."):
            self.media_bridge.command(action.split(".", 1)[1], value)
        else:
            self.on_command(action, value)

    async def _broadcast_loop(self):
        while not self._stopped.is_set():
            if self._clients:
                payload = json.dumps({"type": "state", "state": self.state()}, ensure_ascii=False, separators=(",", ":"))
                dead = []
                for ws in tuple(self._clients):
                    try:
                        await ws.send_str(payload)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    self._clients.discard(ws)
            await asyncio.sleep(0.25)

