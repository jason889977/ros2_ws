import math

import numpy as np
import pytest

from vision_core.transforms import rotation_from_rpy, xarm_pose_to_transform


def test_rotation_from_rpy_composes_extrinsic_xyz():
    rotation = rotation_from_rpy(0.1, 0.2, 0.3)
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
    assert np.allclose(rotation, rz @ ry @ rx)


def test_xarm_pose_to_transform_converts_mm_to_meters():
    transform = xarm_pose_to_transform([1000.0, -250.0, 500.0, 0.0, 0.0, math.pi / 2.0])
    assert np.allclose(transform[:3, 3], [1.0, -0.25, 0.5])


@pytest.mark.parametrize('pose', ([1.0, 2.0], [1.0] * 7))
def test_xarm_pose_to_transform_rejects_wrong_length(pose):
    with pytest.raises(ValueError):
        xarm_pose_to_transform(pose)
