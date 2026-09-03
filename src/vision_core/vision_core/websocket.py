"""Thread-safe WebSocket client manager for dashboard updates."""

from __future__ import annotations

import asyncio
import threading
from typing import Any


class WebSocketManager:
    """Track clients and remove connections whose send operation fails."""

    def __init__(self) -> None:
        self._ws_lock = threading.Lock()
        self._ws_clients: dict[Any, asyncio.AbstractEventLoop] = {}

    def register(self, ws: Any, loop: asyncio.AbstractEventLoop) -> None:
        with self._ws_lock:
            self._ws_clients[ws] = loop

    def unregister(self, ws: Any) -> None:
        with self._ws_lock:
            self._ws_clients.pop(ws, None)

    def broadcast(self, message: dict[str, Any]) -> None:
        with self._ws_lock:
            clients = list(self._ws_clients.items())
        for ws, loop in clients:
            try:
                future = asyncio.run_coroutine_threadsafe(ws.send_json(message), loop)
                future.add_done_callback(lambda done, ws=ws: self._remove_failed(ws, done))
            except Exception:
                self.unregister(ws)

    def _remove_failed(self, ws: Any, future: Any) -> None:
        try:
            future.result()
        except Exception:
            self.unregister(ws)
