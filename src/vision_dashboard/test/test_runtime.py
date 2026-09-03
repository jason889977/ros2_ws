from types import SimpleNamespace

from vision_dashboard.runtime import DashboardRuntime, dashboard_runtime


def test_dashboard_runtime_tracks_current_node():
    runtime = DashboardRuntime()
    first = SimpleNamespace(camera_id='cam1')
    second = SimpleNamespace(camera_id='cam2')

    runtime.set_node(first)
    assert runtime.get_node() is first

    runtime.set_node(second)
    assert runtime.get_node() is second
    assert runtime.get_node().camera_id == 'cam2'


def test_dashboard_runtime_global_singleton_stays_connected():
    node = SimpleNamespace(camera_id='live')
    dashboard_runtime.set_node(node)
    assert dashboard_runtime.get_node() is node


def test_dashboard_runtime_clear_node():
    runtime = DashboardRuntime()
    node = SimpleNamespace(camera_id='cam1')
    runtime.set_node(node)
    runtime.clear_node()
    try:
        runtime.get_node()
        assert False, 'Expected RuntimeError'
    except RuntimeError:
        pass
