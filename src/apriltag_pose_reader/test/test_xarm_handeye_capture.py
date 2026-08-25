import math

import numpy as np
import pytest

from apriltag_pose_reader.xarm_handeye_capture import xarm_pose_to_transform


def test_xarm_pose_converts_mm_and_axis_angle():
    transform = xarm_pose_to_transform([1000.0, -250.0, 500.0, 0.0, 0.0, math.pi / 2.0])
    assert np.allclose(transform[:3, 3], [1.0, -0.25, 0.5])
    assert np.allclose(transform[:3, :3], [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], atol=1e-7)


def test_xarm_pose_pure_roll_is_x_rotation():
    """RPY roll must rotate around the X axis (guards against the rotvec regression)."""
    transform = xarm_pose_to_transform([0.0, 0.0, 0.0, math.pi / 2.0, 0.0, 0.0])
    expected = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0],
        [0.0, 1.0, 0.0],
    ])
    assert np.allclose(transform[:3, :3], expected, atol=1e-7)


def test_xarm_pose_combined_roll_pitch_is_rpy_not_rotvec():
    """Multi-axis orientation must use RPY composition, not axis-angle."""
    transform = xarm_pose_to_transform([0.0, 0.0, 0.0, 0.1, 0.2, 0.3])
    rx = np.array([
        [1.0, 0.0, 0.0],
        [0.0, math.cos(0.1), -math.sin(0.1)],
        [0.0, math.sin(0.1), math.cos(0.1)],
    ])
    ry = np.array([
        [math.cos(0.2), 0.0, math.sin(0.2)],
        [0.0, 1.0, 0.0],
        [-math.sin(0.2), 0.0, math.cos(0.2)],
    ])
    rz = np.array([
        [math.cos(0.3), -math.sin(0.3), 0.0],
        [math.sin(0.3), math.cos(0.3), 0.0],
        [0.0, 0.0, 1.0],
    ])
    assert np.allclose(transform[:3, :3], rz @ ry @ rx, atol=1e-9)


@pytest.mark.parametrize('pose', ([1.0, 2.0], [1.0] * 7, [1.0, 2.0, 3.0, float('nan'), 0.0, 0.0]))
def test_xarm_pose_rejects_invalid_data(pose):
    with pytest.raises(ValueError):
        xarm_pose_to_transform(pose)