from __future__ import annotations

import rclpy
import time
from diagnostic_msgs.msg import DiagnosticArray
from diagnostic_msgs.msg import DiagnosticStatus
from pylon_ros2_camera_interfaces.msg import VisionStatus
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Header


class VisionStatusAggregator(Node):
    def __init__(self, parameter_overrides=None) -> None:
        super().__init__(
            'vision_status_aggregator',
            parameter_overrides=parameter_overrides or [],
        )
        self.declare_parameter('camera_id', 'my_camera')
        self.declare_parameter('diagnostics_topic', '/diagnostics')
        self.declare_parameter('output_topic', '~/status')
        self.declare_parameter('publish_rate_hz', 1.0)
        self.declare_parameter('diagnostic_timeout_s', 5.0)
        self.declare_parameter('expected_components', [''])
        self._camera_id = str(self.get_parameter('camera_id').value)
        self._expected_components = set(
            str(name) for name in self.get_parameter('expected_components').value
            if str(name)
        )
        self._latest = {}
        self._diagnostic_timeout_s = float(
            self.get_parameter('diagnostic_timeout_s').value
        )
        if self._diagnostic_timeout_s <= 0.0:
            raise ValueError('diagnostic_timeout_s must be greater than zero')
        self._diagnostics_sub = self.create_subscription(
            DiagnosticArray,
            str(self.get_parameter('diagnostics_topic').value),
            self._on_diagnostics,
            10,
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

    def _on_diagnostics(self, message: DiagnosticArray) -> None:
        for status in message.status:
            self._latest[status.name] = (status, time.monotonic())

    def _publish_status(self) -> None:
        status = VisionStatus()
        status.header = Header()
        status.header.stamp = self.get_clock().now().to_msg()
        status.camera_id = self._camera_id
        now = time.monotonic()
        fresh = {
            name: item for name, item in self._latest.items()
            if now - item[1] <= self._diagnostic_timeout_s
        }
        status.active_components = len(fresh)
        missing = sorted(self._expected_components - set(fresh))

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

        self._status_pub.publish(status)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VisionStatusAggregator()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
