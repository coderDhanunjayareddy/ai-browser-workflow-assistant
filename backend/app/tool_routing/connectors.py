from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import Any

ConnectorHandler = Callable[[str, dict[str, Any]], dict[str, Any]]

_handlers: dict[str, ConnectorHandler] = {}
_lock = RLock()


def register(name: str, handler: ConnectorHandler) -> None:
    with _lock:
        _handlers[name.strip().lower()] = handler


def available(name: str) -> bool:
    with _lock:
        return name.strip().lower() in _handlers


def call(name: str, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        handler = _handlers.get(name.strip().lower())
    if handler is None:
        raise LookupError(f"Connector {name!r} is not connected")
    return handler(operation, arguments)


def reset_for_testing() -> None:
    with _lock:
        _handlers.clear()
