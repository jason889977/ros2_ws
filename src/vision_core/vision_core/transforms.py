"""Rotation and homogeneous-transform utilities shared by vision packages."""

from __future__ import annotations

import math
import warnings
from typing import Any

import cv2
import numpy as np


def rotation_from_rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Convert XYZ-extrinsic Euler angles to a 3x3 rotation matrix."""
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ], dtype=np.float64)


def rotation_from_quaternion(quaternion: list[float]) -> np.ndarray:
    """Convert a quaternion [x, y, z, w] to a 3x3 rotation matrix."""
    x, y, z, w = quaternion
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 1e-12:
        raise ValueError('Quaternion has zero norm')
    x, y, z, w = [value / norm for value in quaternion]
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def rotation_from_rotvec(rotvec: np.ndarray) -> np.ndarray:
    """Convert a 3-element rotation vector via Rodrigues."""
    return cv2.Rodrigues(np.asarray(rotvec, dtype=np.float64).reshape(3, 1))[0]


def rotation_angle(rotation: np.ndarray) -> float:
    """Compute the rotation angle in radians from a 3x3 matrix."""
    return float(np.linalg.norm(cv2.Rodrigues(rotation)[0]))


def rotation_matrix_to_quaternion(
    rotation: np.ndarray,
    tolerance: float = 1e-3,
) -> tuple[float, float, float, float]:
    """Convert a 3x3 rotation matrix to quaternion (x, y, z, w).

    If *tolerance* > 0 and the input deviates from SO(3) by more than
    *tolerance* (Frobenius norm after SVD projection), a warning is emitted.
    """
    rotation = np.asarray(rotation, dtype=np.float64)
    U, _, Vt = np.linalg.svd(rotation)
    projected = U @ Vt
    if tolerance > 0:
        deviation = float(np.linalg.norm(rotation - projected))
        if deviation > tolerance:
            warnings.warn(
                f'Input matrix deviates from a valid rotation by {deviation:.6g} '
                f'(tolerance={tolerance:.6g}); projected to nearest SO(3).',
                stacklevel=2,
            )
    rotation = projected
    if np.linalg.det(rotation) < 0.0:
        U[:, -1] *= -1.0
        rotation = U @ Vt
    trace = float(np.trace(rotation))
    if trace > 0.0:
        scale = 0.5 / math.sqrt(max(0.0, trace + 1.0))
        qw = 0.25 / scale
        qx = (rotation[2, 1] - rotation[1, 2]) * scale
        qy = (rotation[0, 2] - rotation[2, 0]) * scale
        qz = (rotation[1, 0] - rotation[0, 1]) * scale
    elif rotation[0, 0] > rotation[1, 1] and rotation[0, 0] > rotation[2, 2]:
        scale = 2.0 * math.sqrt(max(0.0, 1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]))
        if scale < 1e-12:
            return (0.0, 0.0, 0.0, 1.0)
        qw = (rotation[2, 1] - rotation[1, 2]) / scale
        qx = 0.25 * scale
        qy = (rotation[0, 1] + rotation[1, 0]) / scale
        qz = (rotation[0, 2] + rotation[2, 0]) / scale
    elif rotation[1, 1] > rotation[2, 2]:
        scale = 2.0 * math.sqrt(max(0.0, 1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]))
        if scale < 1e-12:
            return (0.0, 0.0, 0.0, 1.0)
        qw = (rotation[0, 2] - rotation[2, 0]) / scale
        qx = (rotation[0, 1] + rotation[1, 0]) / scale
        qy = 0.25 * scale
        qz = (rotation[1, 2] + rotation[2, 1]) / scale
    else:
        scale = 2.0 * math.sqrt(max(0.0, 1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]))
        if scale < 1e-12:
            return (0.0, 0.0, 0.0, 1.0)
        qw = (rotation[1, 0] - rotation[0, 1]) / scale
        qx = (rotation[0, 2] + rotation[2, 0]) / scale
        qy = (rotation[1, 2] + rotation[2, 1]) / scale
        qz = 0.25 * scale
    return (qx, qy, qz, qw)


def homogeneous_matrix(rotation: np.ndarray | None = None, translation: Any = None) -> np.ndarray:
    """Build a 4x4 homogeneous matrix from rotation and translation."""
    result = np.eye(4, dtype=np.float64)
    if rotation is not None:
        result[:3, :3] = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    if translation is not None:
        result[:3, 3] = np.asarray(translation, dtype=np.float64).reshape(3)
    return result


def xarm_pose_to_transform(pose: list[float] | tuple[float, ...]) -> np.ndarray:
    """Convert xArm [mm, mm, mm, roll, pitch, yaw] to a 4x4 transform."""
    if len(pose) != 6:
        raise ValueError(f'xArm pose must contain 6 values, got {len(pose)}')
    values = np.asarray(pose, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError('xArm pose contains non-finite values')
    return homogeneous_matrix(
        rotation_from_rpy(values[3], values[4], values[5]),
        values[:3] / 1000.0,
    )


def transform_message_to_matrix(message: Any) -> np.ndarray:
    """Convert a ROS TransformStamped (parent -> child) to a 4x4 matrix."""
    transform = message.transform
    quaternion = [transform.rotation.x, transform.rotation.y, transform.rotation.z, transform.rotation.w]
    translation = [transform.translation.x, transform.translation.y, transform.translation.z]
    if not np.all(np.isfinite(quaternion)) or not np.all(np.isfinite(translation)):
        raise ValueError('AprilTag transform contains non-finite values')
    return homogeneous_matrix(rotation_from_quaternion(quaternion), translation)


def stamp_to_seconds(stamp: Any) -> float:
    """Convert a ROS timestamp (with .sec and .nanosec) to seconds."""
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def generate_aruco_marker(dictionary: Any, marker_id: int, size: int) -> np.ndarray:
    """Generate an ArUco marker image, handling OpenCV version differences."""
    if hasattr(cv2.aruco, 'generateImageMarker'):
        return cv2.aruco.generateImageMarker(dictionary, marker_id, size)
    return cv2.aruco.drawMarker(dictionary, marker_id, size)
