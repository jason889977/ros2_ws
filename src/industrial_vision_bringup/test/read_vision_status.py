"""E2E helper: wait for /<camera>/vision/status and print overall_level.

Exits 0 when overall_level==0 was seen within the timeout, 1 otherwise.
Uses the same rclpy import path as the unit tests (ros2 CLI type loading
can differ per environment).
"""
import sys
import time

import rclpy
from pylon_ros2_camera_interfaces.msg import VisionStatus


def main() -> int:
    camera_id = sys.argv[1] if len(sys.argv) > 1 else 'camera'
    timeout_s = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
    rclpy.init()
    node = rclpy.create_node('vision_status_reader')
    got = {}

    def _cb(msg: VisionStatus) -> None:
        got['level'] = msg.overall_level

    node.create_subscription(
        VisionStatus, f'/{camera_id}/vision/status', _cb, 10)
    deadline = time.monotonic() + timeout_s
    while 'level' not in got and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.5)
    node.destroy_node()
    rclpy.shutdown()
    if got.get('level') == 0:
        print('STATUS_OK')
        return 0
    print(f'STATUS_NOT_OK level={got.get("level")!r}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
