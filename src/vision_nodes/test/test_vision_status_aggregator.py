from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import rclpy
from diagnostic_msgs.msg import DiagnosticStatus
from pylon_ros2_camera_interfaces.msg import VisionStatus
from rclpy.parameter import Parameter

from vision_nodes.vision_status_aggregator import VisionStatusAggregator


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init()
    yield
    if initialized_here and rclpy.ok():
        rclpy.shutdown()


@pytest.fixture
def status_node():
    nodes = []

    def create(expected_components=None):
        if expected_components is None:
            expected_components = ['Scanner Connection']
        parameter_overrides = [
            Parameter('camera_id', value='cam1'),
            Parameter('diagnostics_topic', value='/test/diagnostics'),
            Parameter('output_topic', value='/test/status'),
            Parameter('diagnostic_timeout_s', value=5.0),
        ]
        if expected_components:
            parameter_overrides.append(
                Parameter('expected_components', value=expected_components),
            )
        node = VisionStatusAggregator(parameter_overrides=parameter_overrides)
        node._status_pub = MagicMock()
        nodes.append(node)
        return node

    yield create

    for node in nodes:
        node.destroy_node()


def test_missing_diagnostics_publish_error_status(status_node):
    node = status_node(['Scanner Connection'])
    diagnostic = DiagnosticStatus()
    diagnostic.name = 'Scanner Connection'
    diagnostic.level = DiagnosticStatus.OK
    diagnostic.message = 'Connected'
    node._diag_subscriber._latest_diagnostics[diagnostic.name] = (diagnostic, 0.0)

    with patch(
        'vision_nodes.vision_status_aggregator.time.monotonic',
        return_value=6.0,
    ):
        node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert isinstance(published, VisionStatus)
    assert published.overall_level == VisionStatus.ERROR
    assert published.active_components == 0


def test_no_expected_components_publish_ok_status(status_node):
    node = status_node([])
    node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert published.overall_level == VisionStatus.OK
    assert published.summary == 'No optional components enabled'

def test_latest_error_diagnostic_is_reported(status_node):
    node = status_node()
    diagnostic = DiagnosticStatus()
    diagnostic.name = 'Scanner Connection'
    diagnostic.level = DiagnosticStatus.ERROR
    diagnostic.message = 'Disconnected'
    diagnostic.values.append(SimpleNamespace(key='error_count', value='2'))
    node._diag_subscriber._on_diagnostics(SimpleNamespace(status=[diagnostic]))

    node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert published.overall_level == VisionStatus.ERROR
    assert list(published.component_names) == ['Scanner Connection']
    assert list(published.component_messages) == ['Disconnected']
    assert list(published.metric_names) == ['Scanner Connection.error_count']
    assert list(published.metric_values) == ['2']


def test_mixed_component_levels_are_counted_and_warn_overall(status_node):
    node = status_node()
    warning = DiagnosticStatus()
    warning.name = 'AprilTag Status'
    warning.level = DiagnosticStatus.WARN
    warning.message = 'No recent image data'
    healthy = DiagnosticStatus()
    healthy.name = 'Scanner Connection'
    healthy.level = DiagnosticStatus.OK
    healthy.message = 'Connected'
    node._diag_subscriber._on_diagnostics(SimpleNamespace(status=[warning, healthy]))

    node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert published.overall_level == VisionStatus.WARN
    assert published.active_components == 2
    assert published.warning_components == 1
    assert published.error_components == 0
    assert list(published.component_names) == [
        'AprilTag Status', 'Scanner Connection',
    ]


def test_missing_expected_component_is_reported_as_error(status_node):
    node = status_node()
    node._expected_components = {'AprilTag Status', 'Scanner Connection'}
    diagnostic = DiagnosticStatus()
    diagnostic.name = 'Scanner Connection'
    diagnostic.level = DiagnosticStatus.OK
    diagnostic.message = 'Connected'
    node._diag_subscriber._on_diagnostics(SimpleNamespace(status=[diagnostic]))

    node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert published.overall_level == VisionStatus.ERROR
    assert published.error_components == 1
    assert list(published.component_names) == [
        'Scanner Connection', 'AprilTag Status',
    ]


def test_prefixed_diagnostic_names_match_unprefixed_expected(status_node):
    """diagnostic_updater prefixes status names with '<node_name>: '; the
    aggregator must still match expected entries given without the prefix."""
    node = status_node()
    node._expected_components = {'Scanner Connection', 'AprilTag Status'}
    scanner = DiagnosticStatus()
    scanner.name = 'keyence_sr_node: Scanner Connection'
    scanner.level = DiagnosticStatus.OK
    scanner.message = 'Connected'
    apriltag = DiagnosticStatus()
    apriltag.name = 'apriltag_pose_reader: AprilTag Status'
    apriltag.level = DiagnosticStatus.OK
    apriltag.message = 'Tracking'
    node._diag_subscriber._on_diagnostics(
        SimpleNamespace(status=[scanner, apriltag]))

    node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert published.overall_level == VisionStatus.OK
    assert published.active_components == 2
    assert published.error_components == 0


def test_prefix_match_does_not_mask_really_missing_components(status_node):
    node = status_node()
    node._expected_components = {'Scanner Connection', 'AprilTag Status'}
    scanner = DiagnosticStatus()
    scanner.name = 'keyence_sr_node: Scanner Connection'
    scanner.level = DiagnosticStatus.OK
    scanner.message = 'Connected'
    node._diag_subscriber._on_diagnostics(SimpleNamespace(status=[scanner]))

    node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert published.overall_level == VisionStatus.ERROR
    assert published.error_components == 1
    assert 'AprilTag Status' in published.summary


def test_scan_health_ok_when_no_scans_yet(status_node):
    node = status_node()
    status = MagicMock()
    result = node._scan_health_diagnostic(status)
    status.summary.assert_called_once_with(DiagnosticStatus.OK, 'No scans yet received')
    assert result is status


def test_scan_health_ok_when_recent_scan(status_node):
    node = status_node()
    node._last_scan_mono = 100.0
    node._keyence_scan_count = 3

    status = MagicMock()
    with patch('vision_nodes.vision_status_aggregator.time.monotonic',
               return_value=110.0):
        node._scan_health_diagnostic(status)

    status.summary.assert_called_once_with(DiagnosticStatus.OK, 'Scan rate nominal')


def test_scan_health_warn_when_miss_exceeds_threshold(status_node):
    node = status_node()
    node._last_scan_mono = 100.0
    node._miss_scan_threshold_s = 60.0

    status = MagicMock()
    with patch('vision_nodes.vision_status_aggregator.time.monotonic',
               return_value=200.0):
        node._scan_health_diagnostic(status)

    call_args = status.summary.call_args[0]
    assert call_args[0] == DiagnosticStatus.WARN
    assert '100s' in call_args[1]
    assert 'threshold 60s' in call_args[1]
