"""Frontend↔backend contract tests.

``console.js`` renders directly from these API fields; renaming or removing
any field listed here breaks the console silently. When changing a payload
shape, update ``console.js`` and this file together.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient

from vision_dashboard.app import create_app
from vision_dashboard.runtime import dashboard_runtime
from vision_dashboard.routes import register_dashboard_routes


# Fields referenced by console.js renderStatus/renderCameras/renderHealth.
STATUS_FIELDS = {
    'camera_id', 'overall_level', 'summary', 'active_components',
    'warning_components', 'error_components', 'components',
    'scan_count_total', 'scan_rate_per_minute', 'miss_scan_duration_s',
    'timestamp',
}

# Fields referenced by console.js renderDiagnostics (values carries fps).
DIAGNOSTIC_FIELDS = {
    'name', 'level', 'level_name', 'message', 'hardware_id', 'values',
}

# Fields referenced by console.js renderScans.
SCAN_FIELDS = {'source', 'data', 'timestamp'}


def _full_status() -> dict:
    return {
        'camera_id': 'cam1', 'overall_level': 0, 'overall_level_name': 'OK',
        'summary': 'All components healthy', 'active_components': 4,
        'warning_components': 0, 'error_components': 0,
        'components': [['Scanner Connection', 'Connected']],
        'metrics': {'metric.example': '1'}, 'scan_count_total': 3,
        'keyence_scan_count': 1,
        'scan_rate_per_minute': 12.0, 'miss_scan_duration_s': 4.2,
        'timestamp': 1700000000.0,
    }


def _full_diagnostic() -> dict:
    return {
        'name': 'pylon_ros2_camera_node: camera_availability',
        'level': 0, 'level_name': 'OK', 'message': 'Camera available',
        'hardware_id': 'camera', 'values': {'fps': '29.9'},
    }


@pytest.fixture
def client(tmp_path):
    node = SimpleNamespace(
        camera_id='cam1',
        archive_dir=str(tmp_path),
        event_log_dir=str(tmp_path),
        get_aggregate=lambda: {'cam1': _full_status()},
        get_diagnostics=lambda camera_id=None: {
            'header_age_s': 0.5, 'statuses': [_full_diagnostic()]},
        get_scans=lambda limit: [{
            'source': 'keyence', 'data': 'PAYLOAD',
            'timestamp': '2026-01-01T00:00:00+00:00'}],
        get_latest_image=lambda: None,
        mark_image_request=lambda: None,
    )
    dashboard_runtime.set_node(node)
    static_dir = tmp_path / 'static'
    static_dir.mkdir()
    (static_dir / 'index.html').write_text('<!doctype html>', encoding='utf-8')
    app = create_app(
        str(static_dir),
        lambda a: register_dashboard_routes(
            a, dashboard_runtime, str(static_dir)),
    )
    with TestClient(app) as test_client:
        yield test_client
    dashboard_runtime.clear_node()


def test_aggregate_status_fields_cover_console_contract(client):
    data = client.get('/api/aggregate').json()
    assert data['local_camera_id'] == 'cam1'
    for camera_id, camera in data['cameras'].items():
        missing = STATUS_FIELDS - set(camera)
        assert not missing, f'status fields missing for {camera_id}: {missing}'


def test_diagnostics_fields_cover_console_contract(client):
    data = client.get('/api/diagnostics').json()
    assert 'header_age_s' in data
    for status in data['statuses']:
        missing = DIAGNOSTIC_FIELDS - set(status)
        assert not missing, f'diagnostic fields missing: {missing}'


def test_diagnostics_accepts_camera_id_query(client):
    response = client.get('/api/diagnostics?camera_id=cam9')
    assert response.status_code == 200
    assert 'statuses' in response.json()


def test_scan_fields_cover_console_contract(client):
    for scan in client.get('/api/scans').json():
        missing = SCAN_FIELDS - set(scan)
        assert not missing, f'scan fields missing: {missing}'
