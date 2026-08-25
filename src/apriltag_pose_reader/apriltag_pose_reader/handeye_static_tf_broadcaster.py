"""Publish static transforms from hand-eye calibration YAML or manual parameters."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster


def rotation_matrix_to_quaternion(R: np.ndarray) -> tuple[float, float, float, float]:
    """Convert a 3x3 rotation matrix to quaternion (x, y, z, w)."""
    R = np.asarray(R, dtype=np.float64)
    trace = float(R[0, 0] + R[1, 1] + R[2, 2])
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        qw = 0.25 / s
        qx = (R[2, 1] - R[1, 2]) * s
        qy = (R[0, 2] - R[2, 0]) * s
        qz = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        qw = (R[2, 1] - R[1, 2]) / s
        qx = 0.25 * s
        qy = (R[0, 1] + R[1, 0]) / s
        qz = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        qw = (R[0, 2] - R[2, 0]) / s
        qx = (R[0, 1] + R[1, 0]) / s
        qy = 0.25 * s
        qz = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        qw = (R[1, 0] - R[0, 1]) / s
        qx = (R[0, 2] + R[2, 0]) / s
        qy = (R[1, 2] + R[2, 1]) / s
        qz = 0.25 * s
    return qx, qy, qz, qw


def load_transform_from_yaml(
    yaml_path: str,
    default_parent: str = 'tool0',
    default_child: str = 'camera_optical_frame',
) -> tuple[str, str, np.ndarray, tuple[float, float, float, float]]:
    """Parse OpenCV FileStorage YAML output from handeye_calibrate.py."""
    path = Path(yaml_path)
    if not path.is_file():
        raise FileNotFoundError(f'Hand-eye calibration file not found: {yaml_path}')

    fs = cv2.FileStorage(str(path), cv2.FILE_STORAGE_READ)
    if not fs.isOpened():
        raise ValueError(f'Could not open OpenCV YAML file: {yaml_path}')

    parent_node = fs.getNode('gripper_frame')
    child_node = fs.getNode('camera_frame')
    parent_frame = parent_node.string() if not parent_node.empty() and parent_node.string() else default_parent
    child_frame = child_node.string() if not child_node.empty() and child_node.string() else default_child

    # Eye-in-hand: gripper_to_camera_matrix defines parent(gripper) -> child(camera)
    g2c_node = fs.getNode('gripper_to_camera_matrix')
    if not g2c_node.empty():
        matrix = g2c_node.mat()
    else:
        c2g_node = fs.getNode('camera_to_gripper_matrix')
        if not c2g_node.empty():
            matrix = np.linalg.inv(c2g_node.mat())
        else:
            fs.release()
            raise ValueError(f'No transformation matrix found in {yaml_path}')

    fs.release()
    translation = np.asarray(matrix[:3, 3], dtype=np.float64).reshape(3)
    rotation = np.asarray(matrix[:3, :3], dtype=np.float64)
    quaternion = rotation_matrix_to_quaternion(rotation)
    return parent_frame, child_frame, translation, quaternion


class HandEyeStaticTFBroadcaster(Node):
    """ROS 2 Node to broadcast static transform for hand-eye calibration."""

    def __init__(self, parameter_overrides: list[Any] | None = None) -> None:
        super().__init__(
            'handeye_static_tf_broadcaster',
            parameter_overrides=parameter_overrides or [],
        )
        self.declare_parameter('calibration_file', '')
        self.declare_parameter('parent_frame', 'tool0')
        self.declare_parameter('child_frame', 'camera_optical_frame')
        self.declare_parameter('translation', [0.0, 0.0, 0.0])
        self.declare_parameter('rotation_rpy', [0.0, 0.0, 0.0])

        self._broadcaster = StaticTransformBroadcaster(self)
        calib_file = str(self.get_parameter('calibration_file').value)
        parent_frame = str(self.get_parameter('parent_frame').value)
        child_frame = str(self.get_parameter('child_frame').value)

        if calib_file:
            parent_frame, child_frame, trans, quat = load_transform_from_yaml(
                calib_file, parent_frame, child_frame
            )
        else:
            trans = np.asarray(self.get_parameter('translation').value, dtype=np.float64)
            rpy = [float(v) for v in self.get_parameter('rotation_rpy').value]
            cr, sr = math.cos(rpy[0]), math.sin(rpy[0])
            cp, sp = math.cos(rpy[1]), math.sin(rpy[1])
            cy, sy = math.cos(rpy[2]), math.sin(rpy[2])
            R = np.array([
                [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                [-sp, cp * sr, cp * cr],
            ], dtype=np.float64)
            quat = rotation_matrix_to_quaternion(R)

        tf_msg = TransformStamped()
        tf_msg.header.stamp = self.get_clock().now().to_msg()
        tf_msg.header.frame_id = parent_frame
        tf_msg.child_frame_id = child_frame
        tf_msg.transform.translation.x = float(trans[0])
        tf_msg.transform.translation.y = float(trans[1])
        tf_msg.transform.translation.z = float(trans[2])
        tf_msg.transform.rotation.x = float(quat[0])
        tf_msg.transform.rotation.y = float(quat[1])
        tf_msg.transform.rotation.z = float(quat[2])
        tf_msg.transform.rotation.w = float(quat[3])

        self._broadcaster.sendTransform(tf_msg)
        self.get_logger().info(
            f'Published static TF: {parent_frame} -> {child_frame} '
            f'trans=({trans[0]:.4f}, {trans[1]:.4f}, {trans[2]:.4f})'
        )


def main(args: Any = None) -> None:
    rclpy.init(args=args)
    node = HandEyeStaticTFBroadcaster()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
