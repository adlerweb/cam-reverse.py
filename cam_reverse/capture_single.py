"""``frame`` subcommand: grab a single JPEG from the first discovered camera.
Port of ``capture_single.ts``."""
from __future__ import annotations

import asyncio
from typing import Dict

from . import settings
from .discovery import discover_devices
from .impl import DevSerial
from .logger import logger
from .session import Handlers, Session, make_session, start_video_stream


async def capture_single(discovery_ip: str, out_file: str) -> None:
    sessions: Dict[str, Session] = {}
    done = asyncio.Event()
    dev_ev = discover_devices([discovery_ip])

    def start_session(s: Session) -> None:
        start_video_stream(s)
        logger.info(f"Camera {s.dev_name} is now ready to stream")

    def on_discover(rinfo, dev: DevSerial) -> None:
        if dev.dev_id in sessions:
            logger.info(f"Camera {dev.dev_id} at {rinfo[0]} already discovered, ignoring")
            return
        logger.info(f"Discovered camera {dev.dev_id} at {rinfo[0]}")
        s = make_session(Handlers, dev, rinfo, start_session, 5000)
        sessions[dev.dev_id] = s
        settings.config["cameras"][dev.dev_id] = {"fix_packet_loss": False}

        def on_frame() -> None:
            assembled = b"".join(s.cur_image)
            with open(out_file, "wb") as fh:
                fh.write(assembled)
            logger.info("Got frame. Exiting")
            dev_ev.emit("close")
            s.close()
            done.set()

        s.event_emitter.on("frame", on_frame)

    dev_ev.on("discover", on_discover)
    await done.wait()
