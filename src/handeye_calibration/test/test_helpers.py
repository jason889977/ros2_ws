import numpy as np

from vision_core import closed_loop_errors, homogeneous_matrix


def test_homogeneous_builds_transform_matrix():
    rotation = np.eye(3)
    transform = homogeneous_matrix(rotation, [0.1, -0.2, 0.3])

    assert transform.shape == (4, 4)
    assert np.allclose(transform[:3, :3], rotation)
    assert np.allclose(transform[:3, 3], [0.1, -0.2, 0.3])
    assert np.allclose(transform[3], [0.0, 0.0, 0.0, 1.0])


def test_closed_loop_errors_are_zero_for_consistent_identity_solution():
    rows = [
        (np.eye(3), np.zeros((3, 1)), np.eye(3), np.zeros((3, 1))),
        (np.eye(3), np.array([[0.1], [0.0], [0.0]]), np.eye(3), np.zeros((3, 1))),
    ]

    errors = closed_loop_errors(rows, np.eye(4))

    assert errors[0]['translation_m'] == 0.0
    assert errors[0]['rotation_deg'] == 0.0
