import csv

import cv2
import numpy as np
import pytest

from vision_core import (
    closed_loop_errors as _closed_loop_errors,
    homogeneous_matrix as _homogeneous,
    read_rows,
    solve_hand_eye as solve,
)


def _rotation(axis, angle):
    vector = np.asarray(axis, dtype=np.float64) * angle
    return cv2.Rodrigues(vector)[0]


def _make_rows():
    camera_to_gripper = _homogeneous(_rotation((0.3, 0.8, -0.2), 0.35), [0.04, -0.03, 0.12])
    base_to_target = _homogeneous(_rotation((0.4, -0.3, 0.2), -0.2), [0.5, 0.1, 0.7])
    rows = []
    for index in range(12):
        base_to_gripper = _homogeneous(
            _rotation((1.0, 0.3 + index * 0.02, 0.2), 0.15 + index * 0.11),
            [0.2 + index * 0.01, -0.1 + index * 0.015, 0.35 + index * 0.005],
        )
        target_to_camera = np.linalg.inv(base_to_gripper @ camera_to_gripper) @ base_to_target
        rows.append((
            base_to_gripper[:3, :3],
            base_to_gripper[:3, 3:4],
            target_to_camera[:3, :3],
            target_to_camera[:3, 3:4],
        ))
    return rows, camera_to_gripper


def test_eye_in_hand_solution_matches_synthetic_transform():
    rows, expected = _make_rows()
    rotation, translation = solve(rows, 'park')
    actual = _homogeneous(rotation, translation)
    assert np.allclose(actual, expected, atol=1e-5)
    errors = _closed_loop_errors(rows, actual)
    assert max(item['translation_m'] for item in errors) < 1e-5
    assert max(item['rotation_deg'] for item in errors) < 1e-3


def test_read_rows_rejects_invalid_rotation(tmp_path):
    path = tmp_path / 'poses.csv'
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['gripper2base_r', 'gripper2base_t', 'target2cam_r', 'target2cam_t'])
        writer.writeheader()
        writer.writerow({
            'gripper2base_r': '1 0 0 0 1 0 0 0 2',
            'gripper2base_t': '0 0 0',
            'target2cam_r': '1 0 0 0 1 0 0 0 1',
            'target2cam_t': '0 0 1',
        })
    with pytest.raises(ValueError, match='valid rotation matrix'):
        read_rows(path)