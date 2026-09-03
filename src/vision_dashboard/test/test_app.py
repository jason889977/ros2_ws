from pathlib import Path

from fastapi import FastAPI

from vision_dashboard.app import create_app


def test_create_app_mounts_static_files_and_routes(tmp_path):
    static_dir = tmp_path / 'static'
    static_dir.mkdir()
    (static_dir / 'index.html').write_text('<!doctype html>', encoding='utf-8')

    def register_routes(app):
        @app.get('/health')
        def health():
            return {'ok': True}

    app = create_app(str(static_dir), register_routes)

    assert isinstance(app, FastAPI)
    paths = {route.path for route in app.routes}
    assert '/' not in paths
    assert '/health' in paths
    assert any(path == '/static' or path.startswith('/static/') for path in paths)
    assert Path(static_dir / 'index.html').is_file()


def test_same_origin_post_is_allowed(tmp_path):
    from fastapi.testclient import TestClient

    static_dir = tmp_path / 'static'
    static_dir.mkdir()
    (static_dir / 'index.html').write_text('<!doctype html>', encoding='utf-8')

    def register_routes(app):
        @app.post('/action')
        def action():
            return {'ok': True}

    app = create_app(str(static_dir), register_routes)
    with TestClient(app) as client:
        ok = client.post('/action', headers={'Origin': 'http://testserver'})
        assert ok.status_code == 200
        no_origin = client.post('/action')
        assert no_origin.status_code == 200


def test_cross_origin_post_is_rejected(tmp_path):
    from fastapi.testclient import TestClient

    static_dir = tmp_path / 'static'
    static_dir.mkdir()
    (static_dir / 'index.html').write_text('<!doctype html>', encoding='utf-8')

    def register_routes(app):
        @app.post('/action')
        def action():
            return {'ok': True}

    app = create_app(str(static_dir), register_routes)
    with TestClient(app) as client:
        response = client.post('/action', headers={'Origin': 'http://evil.example'})
        assert response.status_code == 403
