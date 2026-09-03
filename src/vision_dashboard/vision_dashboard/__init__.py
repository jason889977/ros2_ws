"""Framework-independent dashboard infrastructure."""

from .runtime import DashboardRuntime, dashboard_runtime
from .app import create_app
from vision_core.websocket import WebSocketManager

__all__ = ['DashboardRuntime', 'WebSocketManager', 'create_app', 'dashboard_runtime']
