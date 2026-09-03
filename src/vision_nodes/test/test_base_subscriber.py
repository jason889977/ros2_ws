from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from vision_core.diagnostics import DiagnosticsSubscriber


def test_diagnostics_subscriber_tracks_fresh_and_stale_entries():
    subscriber = DiagnosticsSubscriber()
    node = MagicMock()
    subscriber.setup_diagnostics_subscription(node, '/diagnostics', timeout_s=5.0)
    callback = node.create_subscription.call_args.args[2]
    message = SimpleNamespace(status=[SimpleNamespace(name='camera')])

    with patch(
        'vision_core.diagnostics.time.monotonic',
        side_effect=[10.0, 12.0, 30.0],
    ):
        callback(message)
        assert 'camera' in subscriber.get_fresh_diagnostics()
        assert subscriber.get_fresh_diagnostics() == {}


def test_diagnostics_subscriber_rejects_non_positive_timeout():
    subscriber = DiagnosticsSubscriber()

    try:
        subscriber.setup_diagnostics_subscription(MagicMock(), '/diagnostics', 0.0)
    except ValueError as error:
        assert 'greater than zero' in str(error)
    else:
        raise AssertionError('non-positive timeout was accepted')