"""Logging with an extra ``trace`` level below ``debug``.

Port of ``logger.ts`` (winston + custom trace level). Exposes a module-level
``logger`` object configured by :func:`build_logger`; call sites use
``logger.info(...)``, ``logger.warning(...)``, ``logger.log("trace", ...)`` etc.
"""
from __future__ import annotations

import logging
import sys

TRACE = 5
logging.addLevelName(TRACE, "trace")

_LEVELS = {
    "trace": TRACE,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

_COLORS = {
    "trace": "\x1b[37m",
    "debug": "\x1b[34m",
    "info": "\x1b[32m",
    "warning": "\x1b[33m",
    "error": "\x1b[31m",
}
_RESET = "\x1b[0m"


class _ColorFormatter(logging.Formatter):
    def __init__(self, use_color: bool):
        super().__init__("%(asctime)s [%(levelname)s] %(message)s")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if self.use_color:
            color = _COLORS.get(record.levelname, "")
            if color:
                return f"{color}{msg}{_RESET}"
        return msg


class _Logger:
    """Wrapper giving the same call surface as the TS logger."""

    def __init__(self) -> None:
        self._log = logging.getLogger("cam_reverse")

    def configure(self, level: str, colorize) -> None:
        use_color = sys.stdout.isatty() if colorize is None else bool(colorize)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_ColorFormatter(use_color))
        self._log.handlers.clear()
        self._log.addHandler(handler)
        self._log.setLevel(_LEVELS.get(level, logging.INFO))

    def log(self, level_name: str, msg: str) -> None:
        self._log.log(_LEVELS.get(level_name, logging.INFO), msg)

    def trace(self, msg: str) -> None:
        self._log.log(TRACE, msg)

    def debug(self, msg: str) -> None:
        self._log.debug(msg)

    def info(self, msg: str) -> None:
        self._log.info(msg)

    def warning(self, msg: str) -> None:
        self._log.warning(msg)

    def error(self, msg: str) -> None:
        self._log.error(msg)


logger = _Logger()


def build_logger(level: str, colorize=None) -> None:
    logger.configure(level, colorize)
