# vision_dashboard

FastAPI web console for the vision pipeline. The ROS data plane lives in
`vision_nodes.web_dashboard_node`; this package only serves HTTP/WS.

## Layout

| File | Purpose |
|------|---------|
| `app.py` | App factory: CORS disabled, same-origin enforcement for POSTs, static file serving with mtime-based cache busting |
| `routes.py` | Dashboard API: `/api/aggregate`, `/api/diagnostics`, `/api/events`, `/api/camera/stream` (MJPEG, semaphore-limited), `/ws` (versioned `{v:1, type, data}` messages) |
| `pylon_routes.py` | Camera runtime services: exposure/gain set, trigger scan (validated ranges) |
| `runtime.py` | Thread-safe ROS service bridge (`asyncio.wait_for`, no polling) |
| `web_dashboard.py` | Entry point: uvicorn (127.0.0.1) + rclpy executor |
| `static/` | Single-file frontend (`console.js`, `console.css`, `index.html`) |

## Security notes

- No authentication; rely on network isolation. Cross-origin POSTs are
  rejected (403) by middleware.
- Hardware actions (trigger scan) require a frontend confirmation dialog;
  shortcuts use Shift+T/Shift+S.

## Testing

`pytest test/` — includes the frontend/backend contract tests
(`test_contract.py`) that pin every field referenced by `console.js`.
