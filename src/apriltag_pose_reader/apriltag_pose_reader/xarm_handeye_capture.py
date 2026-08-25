"""Collect synchronized xArm7 and AprilTag poses for eye-in-hand calibration."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    import rclpy
    from geometry_msgs.msg import TransformStamped
    from rclpy.node import Node
except ImportError:  # pragma: no cover - allows pure helper tests without ROS
    rclpy = None
    TransformStamped = Any
    Node = object

try:
    from xarm_msgs.msg import RobotMsg
except ImportError as exc:  # pragma: no cover - xarm_ros2 is a deployment dependency
    RobotMsg = Any
    _XARM_IMPORT_ERROR = exc
else:
    _XARM_IMPORT_ERROR = None


def _rotation_from_rotvec(rotvec: np.ndarray) -> np.ndarray:
    return cv2.Rodrigues(np.asarray(rotvec, dtype=np.float64).reshape(3, 1))[0]


def _rotation_from_rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Convert xArm extrinsic roll/pitch/yaw (radians, XYZ convention) to a 3x3 rotation matrix."""
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    # R = Rz(yaw) @ Ry(pitch) @ Rx(roll)
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ], dtype=np.float64)


def _rotation_angle(rotation: np.ndarray) -> float:
    return float(np.linalg.norm(cv2.Rodrigues(rotation)[0]))


def _rotation_from_quaternion(quaternion: list[float]) -> np.ndarray:
    x, y, z, w = quaternion
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 1e-12:
        raise ValueError('AprilTag quaternion has zero norm')
    x, y, z, w = [value / norm for value in quaternion]
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def xarm_pose_to_transform(pose: list[float] | tuple[float, ...]) -> np.ndarray:
    """Convert xArm [mm, mm, mm, roll, pitch, yaw] to a 4x4 transform.

    The orientation part (pose[3:]) of an xArm RobotMsg pose is expressed in
    extrinsic XYZ Euler angles (roll/pitch/yaw in radians), NOT an axis-angle
    rotation vector. Feeding RPY into cv2.Rodrigues yields a wrong rotation
    for any multi-axis orientation.
    """
    if len(pose) != 6:
        raise ValueError(f'xArm pose must contain 6 values, got {len(pose)}')
    values = np.asarray(pose, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError('xArm pose contains non-finite values')
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = _rotation_from_rpy(values[3], values[4], values[5])
    result[:3, 3] = values[:3] / 1000.0
    return result


def transform_message_to_matrix(message: TransformStamped) -> np.ndarray:
    """Convert a ROS TransformStamped (parent -> child) to a 4x4 matrix."""
    transform = message.transform
    quaternion = [transform.rotation.x, transform.rotation.y, transform.rotation.z, transform.rotation.w]
    if not np.all(np.isfinite(quaternion)) or not np.all(np.isfinite([
        transform.translation.x, transform.translation.y, transform.translation.z,
    ])):
        raise ValueError('AprilTag transform contains non-finite values')
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = _rotation_from_quaternion(quaternion)
    result[:3, 3] = [transform.translation.x, transform.translation.y, transform.translation.z]
    return result


def stamp_to_seconds(stamp: Any) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def _flatten_matrix(matrix: np.ndarray) -> str:
    return ' '.join(f'{float(value):.12g}' for value in matrix[:3, :3].reshape(-1))


def _flatten_translation(matrix: np.ndarray) -> str:
    return ' '.join(f'{float(value):.12g}' for value in matrix[:3, 3])


class XArmHandeyeCapture(Node):
    """ROS2 collector; it never commands the robot to move."""

    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__('xarm_handeye_capture')
        self._args = args
        self._latest_robot: tuple[float, np.ndarray] | None = None
        self._latest_target: tuple[float, np.ndarray] | None = None
        self._last_sample: tuple[np.ndarray, np.ndarray] | None = None
        self._samples: list[dict[str, str]] = []
        self._output_dir = Path(args.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self.create_subscription(RobotMsg, args.robot_states_topic, self._on_robot_state, 20)
        self.create_subscription(TransformStamped, args.tag_transform_topic, self._on_tag_transform, 20)
        self.create_timer(1.0 / args.sample_rate_hz, self._try_capture)
        self.get_logger().info(
            f'Collecting xArm eye-in-hand samples from {args.robot_states_topic} and '
            f'{args.tag_transform_topic}; target={args.target_frame or "any"}'
        )

    def _on_robot_state(self, message: RobotMsg) -> None:
        pose = list(message.pose)
        try:
            matrix = xarm_pose_to_transform(pose)
        except ValueError as exc:
            self.get_logger().warning(f'Ignoring invalid xArm pose: {exc}')
            return
        self._latest_robot = (stamp_to_seconds(message.header.stamp), matrix)

    def _on_tag_transform(self, message: TransformStamped) -> None:
        if self._args.target_frame and message.child_frame_id != self._args.target_frame:
            return
        try:
            matrix = transform_message_to_matrix(message)
        except ValueError as exc:
            self.get_logger().warning(f'Ignoring invalid AprilTag transform: {exc}')
            return
        self._latest_target = (stamp_to_seconds(message.header.stamp), matrix)

    def _try_capture(self) -> None:
        if len(self._samples) >= self._args.samples:
            self._write_csv()
            self.get_logger().info('Requested sample count reached; stopping collector.')
            rclpy.shutdown()
            return
        if self._latest_robot is None or self._latest_target is None:
            return
        robot_stamp, robot_matrix = self._latest_robot
        target_stamp, target_matrix = self._latest_target
        if abs(robot_stamp - target_stamp) > self._args.sync_tolerance_s:
            return
        if self._last_sample is not None:
            previous_robot, previous_target = self._last_sample
            translation_delta = np.linalg.norm(robot_matrix[:3, 3] - previous_robot[:3, 3])
            rotation_delta = _rotation_angle(previous_robot[:3, :3].T @ robot_matrix[:3, :3])
            if translation_delta < self._args.min_translation_m and math.degrees(rotation_delta) < self._args.min_rotation_deg:
                return
            if np.linalg.norm(target_matrix[:3, 3] - previous_target[:3, 3]) < self._args.min_target_motion_m:
                return
        self._samples.append({
            'gripper2base_r': _flatten_matrix(robot_matrix),
            'gripper2base_t': _flatten_translation(robot_matrix),
            'target2cam_r': _flatten_matrix(target_matrix),
            'target2cam_t': _flatten_translation(target_matrix),
        })
        self._last_sample = (robot_matrix, target_matrix)
        self._write_csv()
        self.get_logger().info(f'Collected {len(self._samples)}/{self._args.samples} synchronized samples.')

    def _write_csv(self) -> None:
        path = self._output_dir / self._args.csv_name
        with path.open('w', newline='', encoding='utf-8') as stream:
            fieldnames = ['gripper2base_r', 'gripper2base_t', 'target2cam_r', 'target2cam_t']
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self._samples)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Collect xArm7 eye-in-hand calibration samples.')
    parser.add_argument('--robot-states-topic', default='/xarm/robot_states')
    parser.add_argument('--tag-transform-topic', default='/apriltag/transform')
    parser.add_argument('--target-frame', default='', help='AprilTag child frame, e.g. tag36h11:3; empty accepts any tag.')
    parser.add_argument('--output-dir', default='handeye_dataset')
    parser.add_argument('--csv-name', default='poses.csv')
    parser.add_argument('--samples', type=int, default=15)
    parser.add_argument('--sync-tolerance-s', type=float, default=0.1)
    parser.add_argument('--min-translation-m', type=float, default=0.01)
    parser.add_argument('--min-rotation-deg', type=float, default=5.0)
    parser.add_argument('--min-target-motion-m', type=float, default=0.002)
    parser.add_argument('--sample-rate-hz', type=float, default=10.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if rclpy is None:
        raise RuntimeError('ROS2 is unavailable; source /opt/ros/humble/setup.bash first')
    if _XARM_IMPORT_ERROR is not None:
        raise RuntimeError(
            'xarm_msgs is unavailable; install/source xarm_ros2 before starting the collector: '
            f'{_XARM_IMPORT_ERROR}'
        )
    if args.samples < 4 or args.sync_tolerance_s <= 0.0 or args.sample_rate_hz <= 0.0:
        raise ValueError('samples must be >= 4 and time/rate parameters must be positive')
    rclpy.init()
    node = XArmHandeyeCapture(args)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Interrupted; writing collected samples.')
    finally:
        node._write_csv()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())