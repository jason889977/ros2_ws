"""Runtime state shared by the dashboard web layer and ROS node."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

try:
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - handled when FastAPI is unavailable.
    JSONResponse = None


class DashboardRuntime:
    """Keep one dashboard node available to route handlers."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._node: Any | None = None

    def set_node(self, node: Any) -> None:
        with self._lock:
            self._node = node

    def get_node(self) -> Any:
        with self._lock:
            if self._node is None:
                raise RuntimeError('Dashboard node is not initialized')
            return self._node

    def clear_node(self) -> None:
        with self._lock:
            self._node = None


dashboard_runtime = DashboardRuntime()


def _settle_runtime_future(aio_future: 'asyncio.Future', rclpy_future: Any) -> None:
    """Bridge an rclpy Future completion into the event loop."""
    if not aio_future.done():
        aio_future.set_result(rclpy_future)


async def call_runtime_service_async(client: Any, request: Any, unavailable_message: str) -> Any:
    """Call a ROS service asynchronously without blocking the event loop."""
    if JSONResponse is None:
        raise RuntimeError('FastAPI is not available')

    if not client.service_is_ready():
        return JSONResponse({'success': False, 'message': unavailable_message})
    loop = asyncio.get_running_loop()
    done: asyncio.Future = loop.create_future()
    future = client.call_async(request)
    # The callback may fire on the ROS spinner thread, hence call_soon_threadsafe.
    future.add_done_callback(
        lambda _f: loop.call_soon_threadsafe(_settle_runtime_future, done, future))
    try:
        future = await asyncio.wait_for(done, timeout=5.0)
    except asyncio.TimeoutError:
        return JSONResponse({'success': False, 'message': 'Service call timed out'})
    try:
        result = future.result()
    except Exception:
        result = None
    if result is not None:
        return result
    return JSONResponse({'success': False, 'message': 'Service call failed'})


async def handle_service_call(
    client: Any,
    request: Any,
    format_response: Any,
    unavailable_message: str = 'Service unavailable',
) -> Any:
    """Call a ROS service and return a ``JSONResponse`` built from *format_response*.

    *format_response* receives the raw service response and returns a dict.
    If the service call itself fails, an error ``JSONResponse`` is returned.
    """
    if JSONResponse is None:
        raise RuntimeError('FastAPI is not available')

    response = await call_runtime_service_async(client, request, unavailable_message)
    if isinstance(response, JSONResponse):
        return response
    return JSONResponse(format_response(response))
