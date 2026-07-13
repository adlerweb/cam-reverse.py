"""``pair`` subcommand: push wifi credentials to a blank camera on its AP.
Port of ``pair.ts``."""
from __future__ import annotations

import asyncio
import json
from typing import Dict, List

from . import settings
from .discovery import discover_devices
from .handlers import WifiListItem
from .impl import DevSerial, SendListWifi
from .logger import logger
from .session import Handlers, Session, configure_wifi, make_session


async def pair(ssid: str, password: str) -> None:
    logger.info(f"Will configure any devices found to join {ssid}")
    if password == "":
        raise ValueError("You must set a non-zero-length password")

    pairing: Dict[str, Session] = {}
    dev_ev = discover_devices(settings.config["discovery_ips"])

    def on_login(s: Session) -> None:
        logger.info(f"Scanning for Wifi networks on {s.dev_name} -- this may time out")
        s.send(SendListWifi(s))

    def on_discover(rinfo, dev: DevSerial) -> None:
        if dev.dev_id in pairing:
            logger.info(f"Camera {dev.dev_id} at {rinfo[0]} already discovered, ignoring")
            return
        logger.info(f"Discovered camera {dev.dev_id} at {rinfo[0]}")
        s = make_session(Handlers, dev, rinfo, on_login, 10000)
        configured: Dict[str, bool] = {}

        def on_disconnect() -> None:
            logger.info(f"Camera {dev.dev_id} disconnected")
            if configured.get(dev.dev_id):
                logger.info("Press CONTROL+C if you're done setting up your cameras")
            pairing.pop(dev.dev_id, None)
            configured.pop(dev.dev_id, None)

        s.event_emitter.on("disconnect", on_disconnect)
        pairing[dev.dev_id] = s

        def on_list_wifi(items: List[WifiListItem]) -> None:
            matches = [i for i in items if i.ssid == ssid]
            if not matches:
                logger.error(f"Camera could not find SSID '{ssid}'")
                return
            if configured.get(dev.dev_id):
                logger.info("Got two answers from camera, ignoring second")
                return
            match = matches[0]
            logger.info(f"Configuring camera {s.dev_name} on {json.dumps(match.__dict__)}")
            configure_wifi(ssid, password, match.channel)(s)
            configured[dev.dev_id] = True
            logger.info(f"WiFi config for camera {s.dev_name} is done")
            logger.info("Camera should reboot now")

        s.event_emitter.on("ListWifi", on_list_wifi)

    dev_ev.on("discover", on_discover)
    await asyncio.Event().wait()
