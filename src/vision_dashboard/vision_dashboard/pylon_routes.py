"""Pylon camera control routes for the dashboard."""

from __future__ import annotations

try:
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover
    JSONResponse = None

try:
    from pylon_ros2_camera_interfaces.srv import (
        SetBinning,
        SetBrightness,
        SetExposure,
        SetGain,
        SetGamma,
    )
except ModuleNotFoundError:  # pragma: no cover - non-Pylon builds
    SetBinning = SetBrightness = SetExposure = SetGain = SetGamma = None


def register_pylon_routes(app, dashboard_runtime, handle_service_call):
    """Attach Pylon camera control routes to the FastAPI app."""
    if SetExposure is None:
        return

    @app.post('/api/set_exposure')
    async def api_set_exposure(value: float):
        # Upper bound matches the console input field (index.html).
        if not 0.0 < value <= 1000000.0:
            return JSONResponse({'success': False, 'message': 'Exposure must be between 0 and 1000000'}, status_code=400)
        return await handle_service_call(
            dashboard_runtime.get_node().exposure_client,
            SetExposure.Request(target_exposure=value),
            lambda r: {'success': r.success, 'reached': r.reached_exposure_time},
            'Exposure service unavailable',
        )

    @app.post('/api/set_gain')
    async def api_set_gain(value: float):
        if not 0.0 <= value <= 100.0:
            return JSONResponse({'success': False, 'message': 'Gain must be between 0 and 100'}, status_code=400)
        return await handle_service_call(
            dashboard_runtime.get_node().gain_client,
            SetGain.Request(target_gain=value),
            lambda r: {'success': r.success, 'reached': r.reached_gain_value},
            'Gain service unavailable',
        )

    @app.post('/api/set_gamma')
    async def api_set_gamma(value: float):
        if not 0.1 <= value <= 4.0:
            return JSONResponse({'success': False, 'message': 'Gamma must be between 0.1 and 4.0'}, status_code=400)
        return await handle_service_call(
            dashboard_runtime.get_node().gamma_client,
            SetGamma.Request(target_gamma=value),
            lambda r: {'success': r.success, 'target': value, 'reached': r.reached_gamma},
            'Gamma service unavailable',
        )

    @app.post('/api/set_brightness')
    async def api_set_brightness(value: int):
        if not 1 <= value <= 255:
            return JSONResponse({'success': False, 'message': 'Brightness must be between 1 and 255'}, status_code=400)
        return await handle_service_call(
            dashboard_runtime.get_node().brightness_client,
            SetBrightness.Request(target_brightness=value, brightness_continuous=False, exposure_auto=False, gain_auto=False),
            lambda r: {
                'success': r.success, 'target': value,
                'reached': r.reached_brightness,
                'reached_exposure': r.reached_exposure_time,
                'reached_gain': r.reached_gain_value,
            },
            'Brightness service unavailable',
        )

    @app.post('/api/set_binning')
    async def api_set_binning(x: int, y: int):
        if not 1 <= x <= 32 or not 1 <= y <= 32:
            return JSONResponse({'success': False, 'message': 'Binning values must be between 1 and 32'}, status_code=400)
        return await handle_service_call(
            dashboard_runtime.get_node().binning_client,
            SetBinning.Request(target_binning_x=x, target_binning_y=y),
            lambda r: {'success': r.success, 'target': {'x': x, 'y': y}, 'reached': {'x': r.reached_binning_x, 'y': r.reached_binning_y}},
            'Binning service unavailable',
        )
