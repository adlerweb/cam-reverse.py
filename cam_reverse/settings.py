"""Mutable global ``config`` singleton. Port of ``settings.ts``.

As in the TS version, ``load_config`` does a *shallow* merge over the defaults,
and the CLI then overwrites individual keys, so anything reading ``config`` must
read it at call time (via ``from . import settings; settings.config[...]``),
not bind it at import time.

The web UI can persist and reload the config file; ``config_path`` records the
target (the ``--config_file`` argument, or ``config.yml`` in the working
directory as a fallback once something is saved).
"""
from __future__ import annotations

import copy
import os
from typing import Any, Dict, Optional

import yaml

DefaultConfig: Dict[str, Any] = {
    "http_server": {"port": 5000},
    "logging": {"level": "info"},
    "cameras": {},
    "discovery_ips": ["192.168.1.255"],
    "blacklisted_ips": [],
}

config: Dict[str, Any] = copy.deepcopy(DefaultConfig)
config_path: Optional[str] = None

DEFAULT_CONFIG_FILE = "config.yml"


def load_config(path: str) -> None:
    global config, config_path
    with open(path, "r", encoding="utf-8") as fh:
        parsed = yaml.safe_load(fh) or {}
    merged = copy.deepcopy(DefaultConfig)
    merged.update(parsed)
    config = merged
    config_path = path


def apply_config(new: Dict[str, Any]) -> None:
    """Overlay ``new`` onto the live config *in place*.

    Only keys present in ``new`` are touched, so a partial update leaves the
    rest of the config alone; ``cameras`` is merged per-camera so
    runtime-discovered entries and un-edited fields survive. Mutating in place
    keeps the dict identity other modules may hold.
    """
    for key, value in (new or {}).items():
        if key == "cameras" and isinstance(value, dict):
            cams = config.setdefault("cameras", {})
            for cid, cfg in value.items():
                cams[cid] = {**cams.get(cid, {}), **(cfg or {})}
        else:
            config[key] = value


def save_config() -> str:
    """Write the current config to disk, returning the path written."""
    global config_path
    path = config_path or DEFAULT_CONFIG_FILE
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh, sort_keys=False, default_flow_style=False)
    config_path = path
    return path


def reload_config() -> Optional[str]:
    """Re-read the config file from disk and overlay it, returning the path
    read, or ``None`` if there is no readable config file."""
    if not config_path or not os.path.exists(config_path):
        return None
    with open(config_path, "r", encoding="utf-8") as fh:
        parsed = yaml.safe_load(fh) or {}
    apply_config(parsed)
    return config_path
