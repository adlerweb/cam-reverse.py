"""Logging with an extra ``trace`` level below ``debug``.

Port of ``logger.ts`` (winston + custom trace level). Exposes a module-level
``logger`` object configured by :func:`build_logger`; call sites use
``logger.info(...)``, ``logger.warning(...)``, ``logger.log("trace", ...)`` etc.
"""
from __future__ import annotations

import itertools
import logging
import sys
import time
from collections import deque
from typing import Deque, Dict

TRACE = 5
logging.addLevelName(TRACE, "trace")

# In-memory ring buffer of recent records, exposed by the web UI log viewer.
LOG_BUFFER: Deque[Dict] = deque(maxlen=2000)
_seq = itertools.count(1)


class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            LOG_BUFFER.append(
                {
                    "seq": next(_seq),
                    "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
                    "level": record.levelname,
                    "levelno": record.levelno,
                    "message": record.getMessage(),
                }
            )
        except Exception:
            pass

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
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(_ColorFormatter(use_color))
        console.setLevel(_LEVELS.get(level, logging.INFO))
        buffer = _BufferHandler()
        buffer.setLevel(TRACE)
        self._log.handlers.clear()
        self._log.addHandler(console)
        self._log.addHandler(buffer)
        # Capture everything; each handler filters by its own level, so the log
        # viewer can show more detail than the console prints.
        self._log.setLevel(TRACE)

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


def level_no(name: str) -> int:
    """Numeric value for a level name (used to filter the log buffer)."""
    return _LEVELS.get(name, TRACE)


def build_logger(level: str, colorize=None) -> None:
    logger.configure(level, colorize)
