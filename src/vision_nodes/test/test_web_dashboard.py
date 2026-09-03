"""Tests for WebDashboard image conversion diagnostics and thread safety."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from concurrent.futures import ThreadPoolExecutor
import asyncio
import threading
import time

import pytest
import rclpy
from diagnostic_msgs.msg import DiagnosticStatus
from rclpy.parameter import Parameter

from vision_nodes.web_dashboard_node import WebDashboard
from pylon_ros2_camera_interfaces.msg import VisionStatus


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init()
    yield
    if initialized_here and rclpy.ok():
        rclpy.shutdown()


@pytest.fixture
def dashboard():
    node = WebDashboard(parameter_overrides=[
        Parameter('camera_id', value='cam1'),
        Parameter('web_port', value=18080),
    ])
    node._bridge = MagicMock()
    yield node
    node.destroy_node()


def test_image_conversion_success_resets_consecutive_failures(dashboard):
    node = dashboard
    node._image_consecutive_failures = 3
    node._image_failures_total = 5
    node.mark_image_request()

    fake_msg = MagicMock()
    node._bridge.imgmsg_to_cv2.return_value = MagicMock(shape=(480, 640, 3))

    with patch('vision_nodes.web_dashboard_node.cv2') as mock_cv2:
        mock_cv2.resize.return_value = MagicMock(shape=(240, 320, 3))
        mock_cv2.imencode.return_value = (True, MagicMock(tobytes=lambda: b'jpeg'))
        node._on_image(fake_msg)

    assert node._image_consecutive_failures == 0
    assert node._image_failures_total == 5


def test_image_conversion_failure_increments_counters(dashboard):
    node = dashboard
    node._bridge.imgmsg_to_cv2.side_effect = ValueError('bad encoding')
    node.mark_image_request()

    fake_msg = MagicMock()
    node._on_image(fake_msg)

    assert node._image_failures_total == 1
    assert node._image_consecutive_failures == 1


def test_on_image_skips_encoding_without_recent_consumer(dashboard):
    """No web consumer has requested an image, so frames must not encode."""
    node = dashboard
    node._bridge.imgmsg_to_cv2.return_value = MagicMock(shape=(480, 640, 3))

    fake_msg = MagicMock()
    node._on_image(fake_msg)

    assert node._encoding_in_flight is False
    assert node.get_latest_image() is None


def test_image_conversion_multiple_failures_accumulate(dashboard):
    node = dashboard
    node._bridge.imgmsg_to_cv2.side_effect = ValueError('bad encoding')

    fake_msg = MagicMock()
    for _ in range(7):
        node._encode_image(fake_msg)

    assert node._image_failures_total == 7
    assert node._image_consecutive_failures == 7


def test_diagnostic_ok_when_healthy(dashboard):
    node = dashboard
    status = MagicMock()
    result = node._image_conversion_diagnostic(status)

    status.summary.assert_called_once_with(DiagnosticStatus.OK, 'Image conversion healthy')
    assert result is status


def test_diagnostic_warn_after_consecutive_failures(dashboard):
    node = dashboard
    node._image_consecutive_failures = 10
    node._image_failures_total = 10
    status = MagicMock()
    result = node._image_conversion_diagnostic(status)

    status.summary.assert_called_once()
    call_args = status.summary.call_args[0]
    assert call_args[0] == DiagnosticStatus.WARN
    assert '10 consecutive' in call_args[1]
    assert result is status


def test_diagnostic_ok_with_recovering_after_failures(dashboard):
    node = dashboard
    node._image_consecutive_failures = 0
    node._image_failures_total = 3
    status = MagicMock()
    result = node._image_conversion_diagnostic(status)

    status.summary.assert_called_once()
    call_args = status.summary.call_args[0]
    assert call_args[0] == DiagnosticStatus.OK
    assert 'past failures' in call_args[1]


def test_status_broadcast_includes_protocol_version(dashboard):
    node = dashboard

    loop = asyncio.new_event_loop()

    def _run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    loop_thread = threading.Thread(target=_run_loop, daemon=True)
    loop_thread.start()

    received = []

    async def _capture(message):
        received.append(message)

    ws = MagicMock()
    ws.send_json = _capture
    node._websocket_manager._ws_clients[ws] = loop

    msg = VisionStatus()
    msg.camera_id = 'cam1'
    node._on_status(msg)

    time.sleep(0.2)

    assert received, 'expected one broadcast message'
    assert received[0]['v'] == 1
    assert received[0]['type'] == 'status'
    assert received[0]['data']['camera_id'] == 'cam1'

    loop.call_soon_threadsafe(loop.stop)
    loop_thread.join(timeout=2)


def test_broadcast_ws_handles_concurrent_clients(dashboard):
    node = dashboard

    loop = asyncio.new_event_loop()

    def _run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    loop_thread = threading.Thread(target=_run_loop, daemon=True)
    loop_thread.start()

    clients = {}
    for i in range(5):
        ws = MagicMock()

        async def _mock_send_json(*args, **kwargs):
            return None

        ws.send_json = _mock_send_json
        clients[ws] = loop
    node._websocket_manager._ws_clients.update(clients)

    node._broadcast_ws({'type': 'test'})

    time.sleep(0.2)

    assert len(node._websocket_manager._ws_clients) == 5

    loop.call_soon_threadsafe(loop.stop)
    loop_thread.join(timeout=2)


def test_broadcast_ws_removes_failed_clients(dashboard):
    node = dashboard

    loop = asyncio.new_event_loop()

    def _run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    loop_thread = threading.Thread(target=_run_loop, daemon=True)
    loop_thread.start()

    good_ws = MagicMock()

    async def _good_send(*args, **kwargs):
        return None

    good_ws.send_json = _good_send

    bad_ws = MagicMock()

    async def _bad_send(*args, **kwargs):
        raise RuntimeError('connection closed')

    bad_ws.send_json = _bad_send

    node._websocket_manager._ws_clients.update({good_ws: loop, bad_ws: loop})

    node._websocket_manager.broadcast({'type': 'test'})

    time.sleep(0.2)

    assert bad_ws not in node._websocket_manager._ws_clients
    assert good_ws in node._websocket_manager._ws_clients

    loop.call_soon_threadsafe(loop.stop)
    loop_thread.join(timeout=2)


def test_concurrent_broadcast_from_multiple_threads(dashboard):
    node = dashboard

    loop = asyncio.new_event_loop()

    def _run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    loop_thread = threading.Thread(target=_run_loop, daemon=True)
    loop_thread.start()

    future = asyncio.Future()
    future.set_result(None)
    ws = MagicMock()
    ws.send_json = MagicMock(return_value=future)
    node._websocket_manager._ws_clients[ws] = loop

    errors = []

    def _broadcast_worker():
        try:
            for _ in range(50):
                node._broadcast_ws({'type': 'stress'})
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_broadcast_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    loop.call_soon_threadsafe(loop.stop)
    loop_thread.join(timeout=2)

    assert not errors, f'Thread safety violations: {errors}'


def test_status_to_dict_includes_all_fields():
    msg = MagicMock()
    msg.camera_id = 'cam1'
    msg.overall_level = 1
    msg.summary = 'Warning'
    msg.active_components = 2
    msg.warning_components = 1
    msg.error_components = 0
    msg.component_names = ['A']
    msg.component_messages = ['warn msg']
    msg.metric_names = ['m1']
    msg.metric_values = ['v1']
    msg.scan_count_total = 100
    msg.keyence_scan_count = 40
    msg.scan_rate_per_minute = 10.0
    msg.miss_scan_duration_s = 2.5

    result = WebDashboard._status_to_dict(msg)

    assert result['camera_id'] == 'cam1'
    assert result['overall_level'] == 1
    assert result['overall_level_name'] == 'WARN'
    assert result['keyence_scan_count'] == 40
    assert result['scan_count_total'] == 100
    assert 'timestamp' in result


def test_dashboard_read_accessors_return_snapshots(dashboard):
    node = dashboard
    node._status = {'camera_id': 'cam1', 'overall_level': 0}
    node._scan_history.extend([{'data': 'A'}, {'data': 'B'}])
    node._latest_jpeg = b'jpeg'

    status = node.get_status()
    aggregate = node.get_aggregate()
    diagnostics = node.get_diagnostics()

    status['overall_level'] = 2
    aggregate['cam1']['overall_level'] = 2
    diagnostics['statuses'].append({'name': 'mutated'})

    assert node.get_status()['overall_level'] == 0
    assert node.get_aggregate()['cam1']['overall_level'] == 0
    assert node.get_diagnostics()['statuses'] == []
    assert node.get_scans(1) == [{'data': 'B'}]
    assert node.get_latest_image() == b'jpeg'


def test_get_diagnostics_returns_fresh_data_from_subscriber(dashboard):
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue

    node = dashboard
    msg = DiagnosticArray()
    msg.header.stamp.sec = 100
    msg.header.stamp.nanosec = 0
    st = DiagnosticStatus()
    st.name = 'TestComponent'
    st.level = DiagnosticStatus.OK
    st.message = 'all good'
    st.hardware_id = 'hw1'
    st.values = [KeyValue(key='k', value='v')]
    msg.status = [st]

    node._diag_subscriber._on_diagnostics(msg)

    result = node.get_diagnostics()
    assert len(result['statuses']) == 1
    assert result['statuses'][0]['name'] == 'TestComponent'
    assert result['statuses'][0]['level_name'] == 'OK'
    assert result['statuses'][0]['values'] == {'k': 'v'}


def test_dashboard_route_and_websocket_components_are_available():
    import importlib

    dashboard_routes = importlib.import_module('vision_dashboard.routes')
    websocket_manager = importlib.import_module('vision_core.websocket')

    assert hasattr(dashboard_routes, 'register_dashboard_routes')
    assert hasattr(websocket_manager, 'WebSocketManager')
