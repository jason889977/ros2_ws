"""FastAPI route registration for the dashboard."""

from __future__ import annotations

import asyncio
import collections
import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

try:
    from fastapi import WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
except ModuleNotFoundError:  # pragma: no cover - handled when FastAPI is unavailable.
    FileResponse = HTMLResponse = JSONResponse = StreamingResponse = None

from std_srvs.srv import Trigger


def _read_event_entries(node, limit: int) -> list:
    """Read event log segments off the event loop (blocking disk I/O)."""
    base = os.path.join(node.event_log_dir, f'{node.camera_id}_events.jsonl')
    # Rotated segments (event_logger names them <base>.1, .2, ...) hold
    # progressively older entries; the un-suffixed file is the newest.
    rotated = sorted(
        (
            path for path in Path(node.event_log_dir).glob(
                f'{node.camera_id}_events.jsonl.[0-9]*')
            if path.suffix[1:].isdigit()
        ),
        key=lambda path: int(path.suffix[1:]),
        reverse=True,
    )
    segment_paths = [*rotated, Path(base)]
    entries: deque = collections.deque(maxlen=limit)
    for path in segment_paths:
        if not path.is_file():
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = collections.deque(f, maxlen=limit)
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return list(entries)


def register_dashboard_routes(
    app, dashboard_runtime, static_dir: str | None = None,
    *, extra_routes=None,
):
    """Attach dashboard API routes to the provided FastAPI app."""
    if not hasattr(app, 'get'):
        return

    from vision_dashboard.runtime import handle_service_call

    _stream_slots = asyncio.Semaphore(4)

    @app.get('/health')
    async def health():
        return JSONResponse({'status': 'ok'})

    @app.get('/', response_class=HTMLResponse)
    async def serve_index():
        index_path = Path(static_dir or '') / 'index.html'
        html = index_path.read_text(encoding='utf-8')
        # Cache-bust static assets by their newest mtime, so browsers pick
        # up updated JS/CSS without manual version bumps.
        version = max(
            (int(p.stat().st_mtime) for p in Path(static_dir or '').glob('*.*')
             if p.suffix in ('.js', '.css') and p.is_file()),
            default=0,
        )
        return HTMLResponse(html.replace('__ASSET_VER__', str(version)))

    @app.get('/api/aggregate')
    async def api_aggregate():
        node = dashboard_runtime.get_node()
        return JSONResponse({
            'cameras': node.get_aggregate(),
            'local_camera_id': node.camera_id,
        })

    @app.get('/api/diagnostics')
    async def api_diagnostics():
        return JSONResponse(dashboard_runtime.get_node().get_diagnostics())

    @app.get('/api/scans')
    async def api_scans(limit: int = 50):
        limit = max(1, min(limit, 1000))
        return JSONResponse(dashboard_runtime.get_node().get_scans(limit))

    @app.get('/api/camera/image')
    async def api_camera_image():
        node = dashboard_runtime.get_node()
        node.mark_image_request()
        jpeg = node.get_latest_image()
        if jpeg is None:
            return JSONResponse({'error': 'No image available'}, status_code=404)
        return StreamingResponse(iter([jpeg]), media_type='image/jpeg')

    @app.get('/api/camera/stream')
    async def api_camera_stream():
        node = dashboard_runtime.get_node()
        # Cap concurrent MJPEG streams; each holds a live event-loop task.
        if _stream_slots.locked():
            return JSONResponse(
                {'error': 'Too many stream clients'}, status_code=429)
        await _stream_slots.acquire()

        async def generate():
            try:
                while True:
                    node.mark_image_request()
                    jpeg = node.get_latest_image()
                    if jpeg is not None:
                        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass
            finally:
                _stream_slots.release()

        return StreamingResponse(
            generate(), media_type='multipart/x-mixed-replace; boundary=frame')

    @app.get('/api/events')
    async def api_events(limit: int = 50):
        limit = max(1, min(limit, 10000))
        node = dashboard_runtime.get_node()
        # Rotated logs can reach hundreds of MB; never scan them on the
        # event loop or WS heartbeats and streams would stall.
        entries = await asyncio.to_thread(_read_event_entries, node, limit)
        return JSONResponse(entries)

    @app.get('/api/archive')
    async def api_archive():
        node = dashboard_runtime.get_node()
        if not node.archive_dir or not os.path.isdir(node.archive_dir):
            return JSONResponse([])
        files = sorted(
            (f for f in os.listdir(node.archive_dir) if f.endswith('.png')),
            reverse=True,
        )[:200]
        result = []
        for f in files:
            full = os.path.join(node.archive_dir, f)
            try:
                result.append({
                    'filename': f,
                    'size': os.path.getsize(full),
                    'modified': datetime.fromtimestamp(
                        os.path.getmtime(full), tz=timezone.utc).isoformat(),
                })
            except OSError:
                continue
        return JSONResponse(result)

    @app.get('/api/archive/{filename}')
    async def api_archive_file(filename: str):
        node = dashboard_runtime.get_node()
        if not node.archive_dir:
            return JSONResponse({'error': 'Archive not configured'}, status_code=404)
        archive_root = Path(os.path.realpath(node.archive_dir))
        path = Path(os.path.realpath(os.path.join(str(archive_root), filename)))
        if not path.is_relative_to(archive_root):
            return JSONResponse({'error': 'Illegal filename'}, status_code=400)
        if not path.is_file():
            return JSONResponse({'error': 'File not found'}, status_code=404)
        return FileResponse(str(path), media_type='image/png')

    @app.post('/api/trigger_scan')
    async def api_trigger_scan():
        node = dashboard_runtime.get_node()
        return await handle_service_call(
            node.trigger_client, Trigger.Request(),
            lambda r: {'success': r.success, 'message': r.message},
            'Scanner service unavailable',
        )

    if extra_routes is not None:
        extra_routes(app, dashboard_runtime, handle_service_call)

    @app.websocket('/ws')
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        node = dashboard_runtime.get_node()
        loop = asyncio.get_running_loop()
        node.register_websocket(ws, loop)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            node.unregister_websocket(ws)

    return app