from types import SimpleNamespace

import pytest

pytest.importorskip('fastapi')

from fastapi import FastAPI

from vision_dashboard.calibration_routes import register_calibration_routes


def test_registers_complete_calibration_api():
    app = FastAPI()
    shutdown = register_calibration_routes(app, SimpleNamespace())

    paths = {route.path for route in app.routes}
    assert {
        '/api/calibration',
        '/api/calibration/service',
        '/api/calibration/service/toggle',
        '/api/calibration/session',
        '/api/calibration/captures',
        '/api/calibration/preview',
        '/api/calibration/captures/{filename}',
        '/api/calibration/start',
        '/api/calibration/cancel',
        '/api/calibration/apply',
        '/api/calibration/history/{filename}',
    } <= paths
    assert callable(shutdown)