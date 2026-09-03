"""Shared ROS 2 node entry-point helper."""

from __future__ import annotations

import rclpy
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node


def run_node(
    node_class: type[Node],
    *,
    executor_class: type = MultiThreadedExecutor,
    args=None,
) -> None:
    """Instantiate *node_class*, spin with an executor, and clean up on exit."""
    rclpy.init(args=args)
    node = node_class()
    executor = executor_class()
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()