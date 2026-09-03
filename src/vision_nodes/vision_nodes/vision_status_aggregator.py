from __future__ import annotations

import threading
import time
from collections import deque
from diagnostic_msgs.msg import DiagnosticStatus
from diagnostic_updater import DiagnosticStatusWrapper, Updater
from vision_core import run_node
from vision_core import DiagnosticsSubscriber
from pylon_ros2_camera_interfaces.msg import VisionStatus
from rclpy.node import Node
from std_msgs.msg import Header, String


class VisionStatusAggregator(Node):
    """Aggregates diagnostics from vision pipeline components into a consolidated status."""

    def __init__(self, parameter_overrides=None) -> None:
        super().__init__(
            'vision_status_aggregator',
            parameter_overrides=parameter_overrides or [],
        )
        self._diag_subscriber = DiagnosticsSubscriber()
        self.declare_parameter('camera_id', 'my_camera')
        self.declare_parameter('diagnostics_topic', '/diagnostics')
        self.declare_parameter('output_topic', '~/status')
        self.declare_parameter('publish_rate_hz', 1.0)
        self.declare_parameter('diagnostic_timeout_s', 5.0)
        self.declare_parameter('expected_components', [''])
        self.declare_parameter('scanner_barcode_topic', '')
        self.declare_parameter('miss_scan_threshold_s', 60.0)
        self._camera_id = str(self.get_parameter('camera_id').value)
        self._expected_components = set(
            str(name) for name in self.get_parameter('expected_components').value
            if str(name)
        )
        self._diagnostic_timeout_s = float(
            self.get_parameter('diagnostic_timeout_s').value
        )
        if self._diagnostic_timeout_s <= 0.0:
            raise ValueError('diagnostic_timeout_s must be greater than zero')
        self._diag_subscriber.setup_diagnostics_subscription(
            self, str(self.get_parameter('diagnostics_topic').value),
            self._diagnostic_timeout_s,
        )
        self._status_pub = self.create_publisher(
            VisionStatus,
            str(self.get_parameter('output_topic').value),
            10,
        )
        rate_hz = float(self.get_parameter('publish_rate_hz').value)
        if rate_hz <= 0.0:
            raise ValueError('publish_rate_hz must be greater than zero')
        self._timer = self.create_timer(1.0 / rate_hz, self._publish_status)

        self._miss_scan_threshold_s = float(
            self.get_parameter('miss_scan_threshold_s').value
        )
        self._diag_updater = Updater(self)
        self._diag_updater.setHardwareID(self._camera_id)
        self._diag_updater.add('Scan Health', self._scan_health_diagnostic)

        # Production metrics state
        self._scan_lock = threading.Lock()
        self._keyence_scan_count = 0
        self._scan_timestamps: deque[float] = deque()
        self._last_scan_mono: float = 0.0
        self._last_scan_ros_stamp = Header().stamp
        self._rate_window_s = 60.0

        barcode_topic = str(self.get_parameter('scanner_barcode_topic').value)
        if barcode_topic:
            self.create_subscription(
                String, barcode_topic, self._on_keyence_scan, 10)

    def _record_scan(self, source: str) -> None:
        now_mono = time.monotonic()
        ros_stamp = self.get_clock().now().to_msg()
        with self._scan_lock:
            if source == 'keyence':
                self._keyence_scan_count += 1
            self._scan_timestamps.append(now_mono)
            self._last_scan_mono = now_mono
            self._last_scan_ros_stamp = ros_stamp

    def _on_keyence_scan(self, msg: String) -> None:
        self._record_scan('keyence')

    def _missing_components(self, fresh_names: set[str]) -> list[str]:
        """Return expected components without fresh diagnostics.

        Matches exactly first, then falls back to a suffix match so that
        entries may omit the '<node_name>: ' prefix that diagnostic_updater
        adds to every published status name.
        """
        missing = []
        for expected in sorted(self._expected_components):
            if expected in fresh_names:
                continue
            suffix = f': {expected}'
            if any(name.endswith(suffix) for name in fresh_names):
                continue
            missing.append(expected)
        return missing

    def _publish_status(self) -> None:
        status = VisionStatus()
        status.header = Header()
        status.header.stamp = self.get_clock().now().to_msg()
        status.camera_id = self._camera_id
        now = time.monotonic()
        fresh = self._diag_subscriber.get_fresh_diagnostics(now)
        status.active_components = len(fresh)
        missing = self._missing_components(set(fresh))

        if not self._expected_components:
            status.overall_level = VisionStatus.OK
            status.summary = 'No optional components enabled'
        elif missing:
            status.overall_level = VisionStatus.ERROR
            status.summary = 'Expected components missing diagnostics: ' + ', '.join(missing)
        elif not fresh:
            status.overall_level = VisionStatus.STALE
            status.summary = 'No fresh component diagnostics'
        else:
            levels = [item[0].level for item in fresh.values()]
            if any(level >= DiagnosticStatus.ERROR for level in levels):
                status.overall_level = VisionStatus.ERROR
                status.summary = 'One or more components report ERROR'
            elif any(level == DiagnosticStatus.WARN for level in levels):
                status.overall_level = VisionStatus.WARN
                status.summary = 'One or more components report WARN'
            else:
                status.overall_level = VisionStatus.OK
                status.summary = 'All reported components are healthy'

        for item, _ in sorted(fresh.values(), key=lambda value: value[0].name):
            status.component_names.append(item.name)
            status.component_messages.append(item.message)
            for value in item.values:
                status.metric_names.append(f'{item.name}.{value.key}')
                status.metric_values.append(value.value)
            if item.level == DiagnosticStatus.WARN:
                status.warning_components += 1
            elif item.level >= DiagnosticStatus.ERROR:
                status.error_components += 1

        for name in missing:
            status.component_names.append(name)
            status.component_messages.append('No fresh diagnostics')
            status.error_components += 1

        # Production metrics (snapshot under lock, prune stale timestamps)
        with self._scan_lock:
            keyence_count = self._keyence_scan_count
            cutoff = now - self._rate_window_s
            while self._scan_timestamps and self._scan_timestamps[0] < cutoff:
                self._scan_timestamps.popleft()
            scan_rate = float(len(self._scan_timestamps))
            last_stamp = self._last_scan_ros_stamp
            last_mono = self._last_scan_mono

        status.scan_count_total = keyence_count
        status.keyence_scan_count = keyence_count
        status.scan_rate_per_minute = scan_rate
        status.last_scan_timestamp = last_stamp
        status.miss_scan_duration_s = (now - last_mono) if last_mono > 0.0 else 0.0

        self._status_pub.publish(status)

    def _scan_health_diagnostic(
        self, status: DiagnosticStatusWrapper,
    ) -> DiagnosticStatusWrapper:
        now = time.monotonic()
        with self._scan_lock:
            last_mono = self._last_scan_mono
            keyence_count = self._keyence_scan_count
        if last_mono <= 0.0:
            status.summary(DiagnosticStatus.OK, 'No scans yet received')
        else:
            miss = now - last_mono
            if miss > self._miss_scan_threshold_s:
                status.summary(
                    DiagnosticStatus.WARN,
                    f'No scan for {miss:.0f}s (threshold {self._miss_scan_threshold_s:.0f}s)',
                )
            else:
                status.summary(DiagnosticStatus.OK, 'Scan rate nominal')
            status.add('miss_scan_duration_s', f'{miss:.1f}')
        status.add('threshold_s', f'{self._miss_scan_threshold_s:.0f}')
        status.add('keyence_count', str(keyence_count))
        return status

    def destroy_node(self) -> None:
        self._diag_subscriber.teardown()
        super().destroy_node()


def main(args=None) -> None:
    run_node(VisionStatusAggregator, args=args)


if __name__ == '__main__':
    main()