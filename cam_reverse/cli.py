"""Command-line entry point. Port of ``cmd/bin.ts`` (yargs -> argparse)."""
from __future__ import annotations

import argparse
import asyncio
import sys

from . import settings
from .capture_single import capture_single
from .http_server import serve_http
from .logger import build_logger, logger
from .pair import pair


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cam-reverse")
    sub = parser.add_subparsers(dest="command", required=True)

    p_http = sub.add_parser("http_server", help="start http server")
    p_http.add_argument("--color", action="store_true", default=None, help="Use color in logs")
    p_http.add_argument("--config_file", help="Specify config file")
    p_http.add_argument("--log_level", help="Set log level")
    p_http.add_argument("--discovery_ip", help="Camera discovery IP address")
    p_http.add_argument("--port", type=int, help="HTTP Port to listen on")
    p_http.add_argument("--audio", action="store_true", default=None)

    p_pair = sub.add_parser("pair", help="configure a camera")
    p_pair.add_argument("--log_level", default="info", help="Set log level")
    p_pair.add_argument("--discovery_ip", help="Camera discovery IP address")
    p_pair.add_argument("--ssid", required=True, help="Wifi network for the camera to connect to")
    p_pair.add_argument("--password", required=True, help="Wifi network password")

    p_frame = sub.add_parser("frame", help="capture a single frame from the first discovered camera")
    p_frame.add_argument("--log_level", default="info", help="Set log level")
    p_frame.add_argument("--discovery_ip", default="192.168.1.255", help="Camera discovery IP address")
    p_frame.add_argument("--out", required=True, help="Path for output file")

    return parser


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)

    if args.command == "http_server":
        if args.config_file is not None:
            settings.load_config(args.config_file)
        if args.port:
            settings.config["http_server"]["port"] = args.port
        if args.color is not None:
            settings.config["logging"]["use_color"] = args.color
        if args.log_level is not None:
            settings.config["logging"]["level"] = args.log_level
        if args.discovery_ip is not None:
            settings.config["discovery_ips"] = [args.discovery_ip]

        build_logger(settings.config["logging"]["level"], settings.config["logging"].get("use_color"))
        try:
            asyncio.run(serve_http(settings.config["http_server"]["port"]))
        except KeyboardInterrupt:
            pass

    elif args.command == "pair":
        build_logger(args.log_level, None)
        if args.discovery_ip is not None:
            settings.config["discovery_ips"] = [args.discovery_ip]
        try:
            asyncio.run(pair(args.ssid, args.password))
        except KeyboardInterrupt:
            pass

    elif args.command == "frame":
        build_logger(args.log_level, None)
        try:
            asyncio.run(capture_single(args.discovery_ip, args.out))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main(sys.argv[1:])
