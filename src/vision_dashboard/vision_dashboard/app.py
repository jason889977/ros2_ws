"""FastAPI application factory for the vision dashboard."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover - optional dashboard dependency
    FastAPI = None
    StaticFiles = None


_MAX_REQUEST_BODY_SIZE = 1 * 1024 * 1024  # 1 MiB
_UNSAFE_METHODS = {'POST', 'PUT', 'DELETE', 'PATCH'}


def create_app(
    static_dir: str,
    register_routes: Callable[[Any], None] | None = None,
) -> Any:
    """Create the dashboard app without importing ROS node implementations."""
    if FastAPI is None:
        return None
    app = FastAPI(title='Vision Dashboard', docs_url='/api/docs')

    @app.middleware('http')
    async def verify_same_origin(request: Request, call_next):
        """Reject cross-origin state-changing requests (CSRF protection).

        The dashboard is same-origin only, so no CORS is configured. Any
        ``Origin`` header on an unsafe method must match the request host.
        """
        if request.method in _UNSAFE_METHODS:
            origin = request.headers.get('origin')
            if origin:
                host = request.headers.get('host', '')
                if not host or urlparse(origin).netloc != host:
                    return JSONResponse(
                        {'error': 'Cross-origin request rejected'},
                        status_code=403,
                    )
        return await call_next(request)

    @app.middleware('http')
    async def limit_request_body(request: Request, call_next):
        content_length = request.headers.get('content-length')
        if content_length is not None and int(content_length) > _MAX_REQUEST_BODY_SIZE:
            return JSONResponse(
                {'error': 'Request body too large'},
                status_code=413,
            )
        return await call_next(request)

    if StaticFiles is not None and os.path.isdir(static_dir):
        app.mount('/static', StaticFiles(directory=static_dir), name='static')
    if register_routes is not None:
        register_routes(app)
    return app
