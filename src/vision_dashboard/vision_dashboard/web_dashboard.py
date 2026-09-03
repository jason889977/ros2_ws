"""Web dashboard entry point for the industrial vision pipeline.

This module is a thin bootstrap layer:
- Creates the FastAPI application and registers routes.
- Starts the uvicorn server alongside the ROS 2 executor.

All ROS data collection lives in ``vision_nodes.web_dashboard_node.WebDashboard``.
"""

from __future__ import annotations

import os
import threading

import rclpy
from vision_dashboard.runtime import dashboard_runtime
from vision_nodes.web_dashboard_node import WebDashboard
from vision_dashboard.app import FastAPI, create_app  # noqa: F401
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
try:
    import uvicorn
except ImportError:
    uvicorn = None

import vision_dashboard

STATIC_DIR = os.path.join(os.path.dirname(vision_dashboard.__file__), 'static')

from vision_dashboard.routes import register_dashboard_routes  # noqa: E402
from vision_dashboard.pylon_routes import register_pylon_routes  # noqa: E402
from vision_dashboard.calibration_routes import register_calibration_routes  # noqa: E402
from vision_dashboard.handeye_routes import register_handeye_routes  # noqa: E402

app = create_app(
    STATIC_DIR,
    lambda dashboard_app: register_dashboard_routes(
        dashboard_app, dashboard_runtime, STATIC_DIR,
        extra_routes=register_pylon_routes),
)
if app is not None:
    _shutdown_calibration_service = register_calibration_routes(app, dashboard_runtime)
    _shutdown_handeye = register_handeye_routes(app, dashboard_runtime)
else:
    _shutdown_calibration_service = lambda: None
    _shutdown_handeye = lambda: None
HAS_WEB_DASHBOARD = app is not None and uvicorn is not None


def _check_port_available(port: int) -> bool:
    """Return True if the TCP port is free, False if already in use."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _start_uvicorn(port: int) -> tuple:
    """Start uvicorn in a daemon thread. Returns (server, thread).

    Raises RuntimeError if the port is already in use, so the caller
    can fail fast instead of silently running a broken dashboard.
    """
    if not _check_port_available(port):
        raise RuntimeError(
            f'Port {port} is already in use. Another web dashboard or '
            f'stale process may be running. Kill it before restarting.'
        )
    config = uvicorn.Config(
        app, host='127.0.0.1', port=port,
        log_level='warning', access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def _stop_uvicorn(server, thread, logger, timeout: float = 10.0) -> None:
    """Signal uvicorn to exit and wait for the thread."""
    server.should_exit = True
    thread.join(timeout=timeout)
    if thread.is_alive():
        logger.warning(
            f'uvicorn thread did not exit within {timeout:.0f}s; dashboard may linger.'
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = WebDashboard()
    dashboard_runtime.set_node(node)

    executor = MultiThreadedExecutor()
    executor.add_node(node)

    web_server, web_thread = None, None

    if HAS_WEB_DASHBOARD:
        try:
            web_server, web_thread = _start_uvicorn(node.web_port)
        except RuntimeError as exc:
            node.get_logger().fatal(str(exc))
            node.destroy_node()
            rclpy.shutdown()
            raise
    else:
        node.get_logger().warning(
            'FastAPI/uvicorn not installed; web dashboard disabled.')

    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if web_server is not None:
            _stop_uvicorn(web_server, web_thread, node.get_logger())
        _shutdown_calibration_service()
        try:
            _shutdown_handeye()
        except Exception:  # noqa: BLE001 - shutdown is best-effort
            pass
        executor.shutdown()
        node.destroy_node()
        dashboard_runtime.clear_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
