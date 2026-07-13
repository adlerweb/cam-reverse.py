"""HTTP server: MJPEG video + SSE audio + a small web UI. Port of
``http_server.ts`` on aiohttp.

The session layer emits ``frame``/``audio`` synchronously; each connected HTTP
client has an :class:`asyncio.Queue` that those callbacks push into, and the
route handlers drain the queue and write to the response.
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Dict, List

from aiohttp import web

from . import settings
from .discovery import discover_devices
from .exif import add_exif_to_jpeg, create_exif_orientation
from .impl import DevSerial
from .logger import logger
from .session import Handlers, Session, make_session, start_video_stream

BOUNDARY = "a very good boundary line"
_ASSETS = Path(__file__).parent / "assets"

# https://sirv.com/help/articles/rotate-photos-to-be-upright/
oMap = [1, 8, 3, 6]
oMapMirror = [2, 7, 4, 5]
orientations = {o: create_exif_orientation(o) for o in range(1, 9)}

sessions: Dict[str, Session] = {}
video_queues: Dict[str, List[asyncio.Queue]] = {}
audio_queues: Dict[str, List[asyncio.Queue]] = {}

_html_template = (_ASSETS / "asd.html").read_text(encoding="utf-8")
_favicon = (_ASSETS / "cam.ico.gz").read_bytes()


def camera_name(dev_id: str) -> str:
    return settings.config["cameras"][dev_id].get("alias") or dev_id


async def _handle_ui(request: web.Request) -> web.Response:
    dev_id = request.match_info["devId"]
    s = sessions.get(dev_id)
    if s is None:
        return web.Response(status=400, text="invalid ID")
    if not s.connected:
        return web.Response(status=400, text="Nothing online")
    ui = (
        _html_template.replace("${id}", dev_id)
        .replace("${name}", camera_name(dev_id))
        .replace("${audio}", "true" if settings.config["cameras"][dev_id].get("audio") else "false")
    )
    return web.Response(text=ui, content_type="text/html")


async def _handle_audio(request: web.Request) -> web.StreamResponse:
    dev_id = request.match_info["devId"]
    s = sessions.get(dev_id)
    if s is None:
        return web.Response(status=400, text="invalid ID")
    if not s.connected:
        return web.Response(status=400, text="Nothing online")

    resp = web.StreamResponse()
    resp.headers["Content-Type"] = "text/event-stream"
    await resp.prepare(request)
    logger.info(f"Audio stream requested for camera {dev_id}")

    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    audio_queues[dev_id].append(q)
    try:
        while True:
            chunk = await q.get()
            await resp.write(chunk)
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        audio_queues[dev_id].remove(q)
    return resp


async def _handle_favicon(request: web.Request) -> web.Response:
    return web.Response(
        body=_favicon,
        headers={"Content-Type": "image/x-icon", "Content-Encoding": "gzip"},
    )


async def _handle_rotate(request: web.Request) -> web.Response:
    dev_id = request.match_info["devId"]
    cur = settings.config["cameras"].get(dev_id, {}).get("rotate", 0)
    nxt = (cur + 1) % 4
    logger.debug(f"Rotating {dev_id} to {nxt}")
    settings.config["cameras"][dev_id]["rotate"] = nxt
    return web.Response(status=204)


async def _handle_mirror(request: web.Request) -> web.Response:
    dev_id = request.match_info["devId"]
    logger.debug(f"Mirroring {dev_id}")
    cam = settings.config["cameras"][dev_id]
    cam["mirror"] = not cam.get("mirror")
    return web.Response(status=204)


async def _handle_camera(request: web.Request) -> web.StreamResponse:
    dev_id = request.match_info["devId"]
    logger.info(f"Video stream requested for camera {dev_id}")
    s = sessions.get(dev_id)
    if s is None:
        return web.Response(status=400, text=f"Camera {dev_id} not discovered")
    if not s.connected:
        return web.Response(status=400, text=f"Camera {dev_id} offline")

    resp = web.StreamResponse()
    resp.headers["Content-Type"] = f'multipart/x-mixed-replace; boundary="{BOUNDARY}"'
    await resp.prepare(request)

    q: asyncio.Queue = asyncio.Queue(maxsize=10)
    video_queues[dev_id].append(q)
    try:
        while True:
            chunk = await q.get()
            await resp.write(chunk)
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        video_queues[dev_id].remove(q)
        logger.info(f"Video stream closed for camera {dev_id}")
    return resp


async def _handle_index(request: web.Request) -> web.Response:
    parts = [
        "<html><head>",
        '<link rel="shortcut icon" href="/favicon.ico">',
        "<title>All cameras</title></head><body><h1>All cameras</h1><hr/>",
    ]
    for dev_id in sessions:
        parts.append(
            f'<h2>{camera_name(dev_id)}</h2>'
            f'<a href="/ui/{dev_id}"><img src="/camera/{dev_id}"/></a><hr/>'
        )
    parts.append("</body></html>")
    return web.Response(text="".join(parts), content_type="text/html")


def _on_discover(rinfo, dev: DevSerial) -> None:
    if dev.dev_id in sessions:
        logger.info(f"Camera {dev.dev_id} at {rinfo[0]} already discovered, ignoring")
        return

    logger.info(f"Discovered camera {dev.dev_id} at {rinfo[0]}")
    video_queues[dev.dev_id] = []
    audio_queues[dev.dev_id] = []

    def start_session(s: Session) -> None:
        start_video_stream(s)
        logger.info(f"Camera {s.dev_name} is now ready to stream")

    s = make_session(Handlers, dev, rinfo, start_session, 5000)
    sessions[dev.dev_id] = s
    settings.config["cameras"][dev.dev_id] = {
        "rotate": 0,
        "mirror": False,
        "audio": True,
        **settings.config["cameras"].get(dev.dev_id, {}),
    }

    def on_frame() -> None:
        cam = settings.config["cameras"][dev.dev_id]
        orientation = cam["rotate"]
        orientation = oMapMirror[orientation] if cam.get("mirror") else oMap[orientation]
        exif_segment = orientations[orientation]
        jpeg_header = add_exif_to_jpeg(s.cur_image[0], exif_segment)
        assembled = jpeg_header + b"".join(s.cur_image[1:])
        header = (
            f"\r\n--{BOUNDARY}\r\n"
            f"Content-Length: {len(assembled)}\r\n"
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode()
        chunk = header + assembled
        for q in video_queues[dev.dev_id]:
            try:
                q.put_nowait(chunk)
            except asyncio.QueueFull:
                pass

    s.event_emitter.on("frame", on_frame)

    def on_disconnect() -> None:
        logger.info(f"Camera {dev.dev_id} disconnected")
        sessions.pop(dev.dev_id, None)

    s.event_emitter.on("disconnect", on_disconnect)

    if settings.config["cameras"][dev.dev_id].get("audio"):
        def on_audio(payload) -> None:
            b64 = base64.b64encode(payload["data"]).decode("ascii")
            chunk = f"data: {b64}\n\n".encode()
            for q in audio_queues[dev.dev_id]:
                try:
                    q.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass

        s.event_emitter.on("audio", on_audio)


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/ui/{devId}", _handle_ui)
    app.router.add_get("/audio/{devId}", _handle_audio)
    app.router.add_get("/favicon.ico", _handle_favicon)
    app.router.add_get("/rotate/{devId}", _handle_rotate)
    app.router.add_get("/mirror/{devId}", _handle_mirror)
    app.router.add_get("/camera/{devId}", _handle_camera)
    app.router.add_get("/", _handle_index)
    return app


async def serve_http(port: int) -> None:
    dev_ev = discover_devices(settings.config["discovery_ips"])
    dev_ev.on("discover", _on_discover)

    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    logger.info(f"Starting HTTP server on port {port}")
    await site.start()
    # run forever
    await asyncio.Event().wait()
