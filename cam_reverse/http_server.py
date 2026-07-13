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
from .logger import LOG_BUFFER, level_no, logger
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
_discovery_ev = None  # set by serve_http; lets the UI add discovery targets

_html_template = (_ASSETS / "asd.html").read_text(encoding="utf-8")
_index_html = (_ASSETS / "index.html").read_text(encoding="utf-8")
_config_html = (_ASSETS / "config.html").read_text(encoding="utf-8")
_logs_html = (_ASSETS / "logs.html").read_text(encoding="utf-8")
_style_css = (_ASSETS / "style.css").read_text(encoding="utf-8")
_app_js = (_ASSETS / "app.js").read_text(encoding="utf-8")
_favicon = (_ASSETS / "cam.ico.gz").read_bytes()


def camera_name(dev_id: str) -> str:
    return settings.config["cameras"].get(dev_id, {}).get("alias") or dev_id


def _assemble_frame(dev_id: str, s: Session) -> bytes:
    """The current completed frame as a single oriented JPEG."""
    cam = settings.config["cameras"].get(dev_id, {})
    orientation = cam.get("rotate", 0)
    orientation = oMapMirror[orientation] if cam.get("mirror") else oMap[orientation]
    exif_segment = orientations[orientation]
    jpeg_header = add_exif_to_jpeg(s.cur_image[0], exif_segment)
    return jpeg_header + b"".join(s.cur_image[1:])


async def _handle_style(request: web.Request) -> web.Response:
    return web.Response(body=_style_css, content_type="text/css")


async def _handle_app_js(request: web.Request) -> web.Response:
    return web.Response(body=_app_js, content_type="application/javascript")


async def _handle_cameras_api(request: web.Request) -> web.Response:
    data = []
    for dev_id, s in sessions.items():
        cam = settings.config["cameras"].get(dev_id, {})
        data.append(
            {
                "id": dev_id,
                "name": camera_name(dev_id),
                "ip": s.dst_ip,
                "connected": s.connected,
                "rotate": cam.get("rotate", 0),
                "mirror": bool(cam.get("mirror")),
                "audio": bool(cam.get("audio")),
            }
        )
    return web.json_response(data)


async def _handle_camera_save(request: web.Request) -> web.Response:
    dev_id = request.match_info["devId"]
    if dev_id not in settings.config["cameras"]:
        return web.Response(status=404, text="unknown camera")
    # The camera's current rotate/mirror/audio already live in the config; this
    # persists them (creating the file entry if it was only a runtime default).
    try:
        path = settings.save_config()
    except OSError as exc:
        logger.error(f"Could not save camera settings: {exc}")
        return web.Response(status=500, text=f"could not write config: {exc}")
    logger.info(f"Saved settings for camera {dev_id} to {path}")
    return web.json_response({"saved": path})


async def _handle_discover(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    ip = str((body or {}).get("ip", "")).strip()
    remember = bool((body or {}).get("remember"))
    if not ip:
        return web.Response(status=400, text="ip is required")
    if _discovery_ev is None:
        return web.Response(status=503, text="discovery not running")

    _discovery_ev.emit("add_target", ip)
    saved = None
    if remember and ip not in settings.config["discovery_ips"]:
        settings.config["discovery_ips"].append(ip)
        try:
            saved = settings.save_config()
        except OSError as exc:
            logger.error(f"Could not persist discovery IP: {exc}")
    logger.info(f"Added discovery target {ip} via web UI")
    return web.json_response({"added": ip, "saved": saved})


async def _handle_settings_page(request: web.Request) -> web.Response:
    return web.Response(text=_config_html, content_type="text/html")


async def _handle_logs_page(request: web.Request) -> web.Response:
    return web.Response(text=_logs_html, content_type="text/html")


async def _handle_logs_api(request: web.Request) -> web.Response:
    level = request.query.get("level", "trace")
    try:
        after = int(request.query.get("after", "0"))
    except ValueError:
        after = 0
    minno = level_no(level)
    out = [e for e in list(LOG_BUFFER) if e["levelno"] >= minno and e["seq"] > after]
    return web.json_response(out)


async def _handle_config_get(request: web.Request) -> web.Response:
    return web.json_response(settings.config)


async def _handle_config_post(request: web.Request) -> web.Response:
    try:
        new = await request.json()
    except Exception:
        return web.Response(status=400, text="invalid JSON")
    if not isinstance(new, dict):
        return web.Response(status=400, text="config must be an object")
    settings.apply_config(new)
    try:
        path = settings.save_config()
    except OSError as exc:
        logger.error(f"Could not save config: {exc}")
        return web.Response(status=500, text=f"could not write config: {exc}")
    logger.info(f"Config saved to {path} via web UI")
    return web.json_response({"saved": path})


async def _handle_config_reload(request: web.Request) -> web.Response:
    try:
        path = settings.reload_config()
    except (OSError, ValueError) as exc:
        logger.error(f"Could not reload config: {exc}")
        return web.Response(status=500, text=f"could not reload config: {exc}")
    if path is None:
        return web.Response(status=400, text="no config file to reload")
    logger.info(f"Config reloaded from {path} via web UI")
    return web.json_response({"reloaded": path})


async def _handle_snapshot(request: web.Request) -> web.StreamResponse:
    dev_id = request.match_info["devId"]
    s = sessions.get(dev_id)
    if s is None:
        return web.Response(status=400, text=f"Camera {dev_id} not discovered")
    if not s.connected:
        return web.Response(status=400, text=f"Camera {dev_id} offline")

    # Grab the next completed frame off the session's event stream.
    fut: asyncio.Future = asyncio.get_event_loop().create_future()

    def on_frame_once() -> None:
        if fut.done():
            return
        try:
            fut.set_result(_assemble_frame(dev_id, s))
        except Exception as exc:  # malformed frame; report rather than hang
            fut.set_exception(exc)

    s.event_emitter.on("frame", on_frame_once)
    try:
        data = await asyncio.wait_for(fut, timeout=10)
    except asyncio.TimeoutError:
        return web.Response(status=504, text="no frame within timeout")
    except Exception as exc:
        return web.Response(status=500, text=f"frame error: {exc}")
    finally:
        s.event_emitter.off("frame", on_frame_once)
    return web.Response(body=data, content_type="image/jpeg")


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
    logger.info(f"Audio stream requested for camera {dev_id} ({s.dst_ip})")

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
    s = sessions.get(dev_id)
    if s is None:
        logger.info(f"Video stream requested for unknown camera {dev_id} from client {request.remote}")
        return web.Response(status=400, text=f"Camera {dev_id} not discovered")
    if not s.connected:
        return web.Response(status=400, text=f"Camera {dev_id} offline")
    cam_ip = s.dst_ip
    logger.info(f"Video stream requested for camera {dev_id} ({cam_ip})")

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
        logger.info(f"Video stream closed for camera {dev_id} ({cam_ip})")
    return resp


async def _handle_index(request: web.Request) -> web.Response:
    # The gallery is data-driven: the page fetches /api/cameras and renders cards.
    return web.Response(text=_index_html, content_type="text/html")


def _on_discover(rinfo, dev: DevSerial) -> None:
    if dev.dev_id in sessions:
        logger.info(f"Camera {dev.dev_id} at {rinfo[0]} already discovered, ignoring")
        return

    cam_ip = rinfo[0]
    logger.info(f"Discovered camera {dev.dev_id} at {cam_ip}")
    video_queues[dev.dev_id] = []
    audio_queues[dev.dev_id] = []

    def start_session(s: Session) -> None:
        start_video_stream(s)
        logger.info(f"Camera {s.dev_name} ({cam_ip}) is now ready to stream")

    s = make_session(Handlers, dev, rinfo, start_session, 5000)
    sessions[dev.dev_id] = s
    settings.config["cameras"][dev.dev_id] = {
        "rotate": 0,
        "mirror": False,
        "audio": True,
        **settings.config["cameras"].get(dev.dev_id, {}),
    }

    def on_frame() -> None:
        assembled = _assemble_frame(dev.dev_id, s)
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
        logger.info(f"Camera {dev.dev_id} ({cam_ip}) disconnected")
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


@web.middleware
async def _log_requests(request: web.Request, handler):
    logger.debug(f"HTTP {request.method} {request.path_qs} from {request.remote}")
    try:
        resp = await handler(request)
    except web.HTTPException as exc:
        logger.debug(f"HTTP {request.method} {request.path_qs} -> {exc.status}")
        raise
    logger.debug(f"HTTP {request.method} {request.path_qs} -> {resp.status}")
    return resp


def build_app() -> web.Application:
    app = web.Application(middlewares=[_log_requests])
    app.router.add_get("/style.css", _handle_style)
    app.router.add_get("/app.js", _handle_app_js)
    app.router.add_get("/api/cameras", _handle_cameras_api)
    app.router.add_post("/api/discover", _handle_discover)
    app.router.add_post("/api/cameras/{devId}/save", _handle_camera_save)
    app.router.add_get("/settings", _handle_settings_page)
    app.router.add_get("/logs", _handle_logs_page)
    app.router.add_get("/api/logs", _handle_logs_api)
    app.router.add_get("/api/config", _handle_config_get)
    app.router.add_post("/api/config", _handle_config_post)
    app.router.add_post("/api/config/reload", _handle_config_reload)
    app.router.add_get("/ui/{devId}", _handle_ui)
    app.router.add_get("/audio/{devId}", _handle_audio)
    app.router.add_get("/favicon.ico", _handle_favicon)
    app.router.add_get("/rotate/{devId}", _handle_rotate)
    app.router.add_get("/mirror/{devId}", _handle_mirror)
    app.router.add_get("/camera/{devId}", _handle_camera)
    app.router.add_get("/snapshot/{devId}", _handle_snapshot)
    app.router.add_get("/", _handle_index)
    return app


async def serve_http(port: int) -> None:
    global _discovery_ev
    dev_ev = discover_devices(settings.config["discovery_ips"])
    dev_ev.on("discover", _on_discover)
    _discovery_ev = dev_ev

    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    logger.info(f"Starting HTTP server on port {port}")
    await site.start()
    # run forever
    await asyncio.Event().wait()
