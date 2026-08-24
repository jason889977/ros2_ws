import math

import numpy as np
import pytest

from apriltag_pose_reader.xarm_handeye_capture import xarm_pose_to_transform


def test_xarm_pose_converts_mm_and_axis_angle():
    transform = xarm_pose_to_transform([1000.0, -250.0, 500.0, 0.0, 0.0, math.pi / 2.0])
    assert np.allclose(transform[:3, 3], [1.0, -0.25, 0.5])
    assert np.allclose(transform[:3, :3], [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], atol=1e-7)


@pytest.mark.parametrize('pose', ([1.0, 2.0], [1.0] * 7, [1.0, 2.0, 3.0, float('nan'), 0.0, 0.0]))
def test_xarm_pose_rejects_invalid_data(pose):
    with pytest.raises(ValueError):
        xarm_pose_to_transform(pose)