"""Minimal synchronous EventEmitter, mirroring node's ``events.EventEmitter``.

The TS code wires the layers together with ``.on(name, cb)`` / ``.emit(name,
...)``; keeping the same shape makes the port a near-transliteration.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, DefaultDict, List


class EventEmitter:
    def __init__(self) -> None:
        self._listeners: DefaultDict[str, List[Callable]] = defaultdict(list)

    def on(self, event: str, cb: Callable) -> "EventEmitter":
        self._listeners[event].append(cb)
        return self

    def emit(self, event: str, *args) -> bool:
        listeners = list(self._listeners.get(event, ()))
        for cb in listeners:
            cb(*args)
        return bool(listeners)
