import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from pylon_ros2_camera_interfaces.msg import VisionStatus
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter

from vision_nodes.vision_status_aggregator import (
    VisionStatusAggregator,
)


def test_status_aggregator_uses_real_ros_topics():
    rclpy.init()
    aggregator = VisionStatusAggregator(parameter_overrides=[
        Parameter('camera_id', Parameter.Type.STRING, 'graph_cam'),
        Parameter(
            'diagnostics_topic', Parameter.Type.STRING, '/graph_cam/diagnostics'
        ),
        Parameter(
            'output_topic', Parameter.Type.STRING, '/graph_cam/vision/status'
        ),
        Parameter('publish_rate_hz', Parameter.Type.DOUBLE, 20.0),
    ])
    source = Node('fake_diagnostics_source')
    observer = Node('status_observer')
    diagnostics_pub = source.create_publisher(
        DiagnosticArray, '/graph_cam/diagnostics', 10,
    )
    received = []
    observer.create_subscription(
        VisionStatus,
        '/graph_cam/vision/status',
        received.append,
        10,
    )
    executor = SingleThreadedExecutor()
    for node in (aggregator, source, observer):
        executor.add_node(node)

    message = DiagnosticArray()
    diagnostic = DiagnosticStatus()
    diagnostic.name = 'Fake Camera'
    diagnostic.level = DiagnosticStatus.OK
    diagnostic.message = 'Image stream healthy'
    diagnostic.values.append(KeyValue(key='fps', value='10.0'))
    message.status.append(diagnostic)

    deadline = time.monotonic() + 3.0
    try:
        while time.monotonic() < deadline and (
            not received or not received[-1].component_names
        ):
            diagnostics_pub.publish(message)
            executor.spin_once(timeout_sec=0.05)

        assert received
        status = received[-1]
        assert status.camera_id == 'graph_cam'
        assert status.overall_level == VisionStatus.OK
        assert list(status.component_names) == ['Fake Camera']
        assert list(status.metric_names) == ['Fake Camera.fps']
        assert list(status.metric_values) == ['10.0']
    finally:
        for node in (aggregator, source, observer):
            node.destroy_node()
        rclpy.shutdown()