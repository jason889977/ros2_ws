from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from diagnostic_msgs.msg import DiagnosticStatus
from builtin_interfaces.msg import Time
from pylon_ros2_camera_interfaces.msg import VisionStatus

from industrial_vision_bringup.vision_status_aggregator import VisionStatusAggregator


def make_status_node(expected_components=None):
    node = VisionStatusAggregator.__new__(VisionStatusAggregator)
    node._camera_id = 'cam1'
    node._latest = {}
    if expected_components is None:
        expected_components = ['Scanner Connection']
    node._expected_components = set(expected_components)
    node._diagnostic_timeout_s = 5.0
    node._status_pub = MagicMock()
    node.get_clock = lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(to_msg=lambda: Time())
    )
    return node


def test_missing_diagnostics_publish_error_status():
    node = make_status_node(['Scanner Connection'])
    diagnostic = DiagnosticStatus()
    diagnostic.name = 'Scanner Connection'
    diagnostic.level = DiagnosticStatus.OK
    diagnostic.message = 'Connected'
    node._latest[diagnostic.name] = (diagnostic, 0.0)

    with patch(
        'industrial_vision_bringup.vision_status_aggregator.time.monotonic',
        return_value=6.0,
    ):
        node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert isinstance(published, VisionStatus)
    assert published.overall_level == VisionStatus.ERROR
    assert published.active_components == 0


def test_no_expected_components_publish_ok_status():
    node = make_status_node([])
    node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert published.overall_level == VisionStatus.OK
    assert published.summary == 'No optional components enabled'

def test_latest_error_diagnostic_is_reported():
    node = make_status_node()
    diagnostic = DiagnosticStatus()
    diagnostic.name = 'Scanner Connection'
    diagnostic.level = DiagnosticStatus.ERROR
    diagnostic.message = 'Disconnected'
    diagnostic.values.append(SimpleNamespace(key='error_count', value='2'))
    node._on_diagnostics(SimpleNamespace(status=[diagnostic]))

    node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert published.overall_level == VisionStatus.ERROR
    assert list(published.component_names) == ['Scanner Connection']
    assert list(published.component_messages) == ['Disconnected']
    assert list(published.metric_names) == ['Scanner Connection.error_count']
    assert list(published.metric_values) == ['2']


def test_mixed_component_levels_are_counted_and_warn_overall():
    node = make_status_node()
    warning = DiagnosticStatus()
    warning.name = 'QR Detector Status'
    warning.level = DiagnosticStatus.WARN
    warning.message = 'No recent image data'
    healthy = DiagnosticStatus()
    healthy.name = 'Scanner Connection'
    healthy.level = DiagnosticStatus.OK
    healthy.message = 'Connected'
    node._on_diagnostics(SimpleNamespace(status=[warning, healthy]))

    node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert published.overall_level == VisionStatus.WARN
    assert published.active_components == 2
    assert published.warning_components == 1
    assert published.error_components == 0
    assert list(published.component_names) == [
        'QR Detector Status', 'Scanner Connection',
    ]


def test_missing_expected_component_is_reported_as_error():
    node = make_status_node()
    node._expected_components = {'QR Detector Status', 'Scanner Connection'}
    diagnostic = DiagnosticStatus()
    diagnostic.name = 'Scanner Connection'
    diagnostic.level = DiagnosticStatus.OK
    diagnostic.message = 'Connected'
    node._on_diagnostics(SimpleNamespace(status=[diagnostic]))

    node._publish_status()

    published = node._status_pub.publish.call_args.args[0]
    assert published.overall_level == VisionStatus.ERROR
    assert published.error_components == 1
    assert list(published.component_names) == [
        'Scanner Connection', 'QR Detector Status',
    ]
