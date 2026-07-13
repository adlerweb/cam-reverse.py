"""Mutable global ``config`` singleton. Port of ``settings.ts``.

As in the TS version, ``load_config`` does a *shallow* merge over the defaults,
and the CLI then overwrites individual keys, so anything reading ``config`` must
read it at call time (via ``from . import settings; settings.config[...]``),
not bind it at import time.
"""
from __future__ import annotations

import copy
from typing import Any, Dict

import yaml

DefaultConfig: Dict[str, Any] = {
    "http_server": {"port": 5000},
    "logging": {"level": "info"},
    "cameras": {},
    "discovery_ips": ["192.168.1.255"],
    "blacklisted_ips": [],
}

config: Dict[str, Any] = copy.deepcopy(DefaultConfig)


def load_config(path: str) -> None:
    global config
    with open(path, "r", encoding="utf-8") as fh:
        parsed = yaml.safe_load(fh) or {}
    merged = copy.deepcopy(DefaultConfig)
    merged.update(parsed)
    config = merged
