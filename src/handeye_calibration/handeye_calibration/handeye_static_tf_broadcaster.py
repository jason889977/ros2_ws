"""Publish static transforms from hand-eye calibration YAML or manual parameters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from vision_core import rotation_from_rpy, rotation_matrix_to_quaternion, run_node
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster

try:
    from apriltag_pose_reader_interfaces.srv import ReloadCalibration
except ImportError:
    ReloadCalibration = None


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
            raw = c2g_node.mat()
            if raw.shape != (4, 4):
                fs.release()
                raise ValueError(f'camera_to_gripper_matrix has unexpected shape: {raw.shape}')
            det = np.linalg.det(raw)
            if abs(det) < 1e-12:
                fs.release()
                raise ValueError('camera_to_gripper_matrix is singular')
            matrix = np.linalg.inv(raw)
        else:
            fs.release()
            raise ValueError(f'No transformation matrix found in {yaml_path}')

    fs.release()
    if matrix.shape != (4, 4):
        raise ValueError(f'Transform matrix has unexpected shape: {matrix.shape}')
    translation = np.asarray(matrix[:3, 3], dtype=np.float64).reshape(3)
    rotation = np.asarray(matrix[:3, :3], dtype=np.float64)
    if not np.all(np.isfinite(translation)) or not np.all(np.isfinite(rotation)):
        raise ValueError('Transform matrix contains non-finite values')
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
        self._default_parent = str(self.get_parameter('parent_frame').value)
        self._default_child = str(self.get_parameter('child_frame').value)

        if ReloadCalibration is not None:
            self._reload_srv = self.create_service(
                ReloadCalibration, '~/reload_calibration', self._on_reload,
            )
        else:
            self._reload_srv = None

        calib_file = str(self.get_parameter('calibration_file').value)
        if calib_file:
            self._publish_from_yaml(calib_file)
        else:
            self._publish_from_rpy()

    def _publish_from_yaml(self, yaml_path: str) -> None:
        parent_frame, child_frame, trans, quat = load_transform_from_yaml(
            yaml_path, self._default_parent, self._default_child,
        )
        self._send_transform(parent_frame, child_frame, trans, quat)

    def _publish_from_rpy(self) -> None:
        trans = np.asarray(self.get_parameter('translation').value, dtype=np.float64)
        rpy = [float(v) for v in self.get_parameter('rotation_rpy').value]
        R = rotation_from_rpy(rpy[0], rpy[1], rpy[2])
        quat = rotation_matrix_to_quaternion(R)
        self._send_transform(self._default_parent, self._default_child, trans, quat)

    def _send_transform(
        self,
        parent_frame: str,
        child_frame: str,
        trans: np.ndarray,
        quat: tuple[float, float, float, float],
    ) -> None:
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

    def _on_reload(self, request, response):
        yaml_path = request.calibration_file
        try:
            self._publish_from_yaml(yaml_path)
            response.success = True
            response.message = f'Reloaded calibration from {yaml_path}'
        except (FileNotFoundError, OSError, ValueError, cv2.error,
            np.linalg.LinAlgError) as exc:
            response.success = False
            response.message = f'Failed to reload: {exc}'
        return response


def main(args: Any = None) -> None:
    run_node(HandEyeStaticTFBroadcaster, args=args)


if __name__ == '__main__':
    main()