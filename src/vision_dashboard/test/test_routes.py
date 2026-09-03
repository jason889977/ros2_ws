from types import SimpleNamespace

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient

from vision_dashboard.runtime import dashboard_runtime
from vision_dashboard.routes import register_dashboard_routes
from vision_dashboard.app import create_app


@pytest.fixture
def client(tmp_path):
    node = SimpleNamespace(
        camera_id='cam1',
        archive_dir=str(tmp_path),
        event_log_dir=str(tmp_path),
        get_status=lambda: {'camera_id': 'cam1', 'overall_level': 0},
        get_aggregate=lambda: {'cam1': {'camera_id': 'cam1'}},
        get_diagnostics=lambda camera_id=None: {'statuses': []},
        get_scans=lambda limit: [],
        get_latest_image=lambda: None,
        mark_image_request=lambda: None,
    )
    dashboard_runtime.set_node(node)
    static_dir = tmp_path / 'static'
    static_dir.mkdir()
    (static_dir / 'index.html').write_text(
        '<!doctype html><link href="/static/console.css?v=__ASSET_VER__">',
        encoding='utf-8')
    app = create_app(
        str(static_dir),
        lambda a: register_dashboard_routes(a, dashboard_runtime, str(static_dir)),
    )
    with TestClient(app) as test_client:
        yield test_client
    dashboard_runtime.clear_node()


def test_aggregate_route_includes_local_camera_id(client):
    response = client.get('/api/aggregate')
    assert response.status_code == 200
    data = response.json()
    assert data == {
        'cameras': {'cam1': {'camera_id': 'cam1'}},
        'local_camera_id': 'cam1',
    }


def test_health_route_reports_liveness(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_camera_image_returns_not_found_without_frame(client):
    response = client.get('/api/camera/image')
    assert response.status_code == 404
    assert response.json()['error'] == 'No image available'


def test_archive_route_rejects_path_traversal(client):
    response = client.get('/api/archive/../outside.png')
    assert response.status_code in (400, 404)


def test_aggregate_route(client):
    response = client.get('/api/aggregate')
    assert response.status_code == 200
    assert response.json()['cameras'] == {'cam1': {'camera_id': 'cam1'}}


def test_diagnostics_route(client):
    response = client.get('/api/diagnostics')
    assert response.status_code == 200
    assert response.json() == {'statuses': []}


def test_scans_route(client):
    response = client.get('/api/scans')
    assert response.status_code == 200
    assert response.json() == []


def test_events_route_empty(client, tmp_path):
    response = client.get('/api/events')
    assert response.status_code == 200
    assert response.json() == []


def test_events_route_with_data(client, tmp_path):
    log_file = tmp_path / 'cam1_events.jsonl'
    log_file.write_text('{"event":"test","timestamp":"2026-01-01T00:00:00"}\n')
    response = client.get('/api/events')
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]['event'] == 'test'


def test_archive_route_empty(client, tmp_path):
    response = client.get('/api/archive')
    assert response.status_code == 200
    assert response.json() == []


def test_archive_route_with_files(client, tmp_path):
    (tmp_path / 'frame_001.png').write_bytes(b'\x89PNG\r\n')
    response = client.get('/api/archive')
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]['filename'] == 'frame_001.png'


def test_archive_file_not_found(client, tmp_path):
    response = client.get('/api/archive/nonexistent.png')
    assert response.status_code == 404


def test_events_route_includes_rotated_segments(client, tmp_path):
    (tmp_path / 'cam1_events.jsonl.2').write_text(
        '{"event":"oldest"}\n', encoding='utf-8')
    (tmp_path / 'cam1_events.jsonl.1').write_text(
        '{"event":"rotated"}\n', encoding='utf-8')
    (tmp_path / 'cam1_events.jsonl').write_text(
        '{"event":"current"}\n', encoding='utf-8')
    response = client.get('/api/events?limit=10')
    assert response.status_code == 200
    events = [entry['event'] for entry in response.json()]
    assert events == ['oldest', 'rotated', 'current']


def test_events_route_limit_keeps_newest_entries(client, tmp_path):
    lines = ''.join(f'{{"event":"e{i}"}}\n' for i in range(5))
    (tmp_path / 'cam1_events.jsonl').write_text(lines, encoding='utf-8')
    response = client.get('/api/events?limit=2')
    events = [entry['event'] for entry in response.json()]
    assert events == ['e3', 'e4']


def test_index_route_injects_asset_version(client, tmp_path):
    static_dir = tmp_path / 'static'
    (static_dir / 'console.js').write_text('// js', encoding='utf-8')
    response = client.get('/')
    assert response.status_code == 200
    assert '__ASSET_VER__' not in response.text
    assert f'?v=' in response.text
