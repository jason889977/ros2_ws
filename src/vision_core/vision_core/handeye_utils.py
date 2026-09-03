"""Shared hand-eye calibration sample collection and solving logic."""

from __future__ import annotations

import csv
import math

import cv2
import numpy as np

from .transforms import homogeneous_matrix, rotation_angle

HAND_EYE_ALGORITHMS = {
    'tsai': cv2.CALIB_HAND_EYE_TSAI,
    'park': cv2.CALIB_HAND_EYE_PARK,
    'horaud': cv2.CALIB_HAND_EYE_HORAUD,
    'daniilidis': cv2.CALIB_HAND_EYE_DANIILIDIS,
}


def _parse_values(value, size, field, row_number):
    try:
        values = np.asarray(
            [float(item) for item in value.replace(',', ' ').split()],
            dtype=np.float64,
        )
    except ValueError as exc:
        raise ValueError(f'Row {row_number}: {field} contains a non-numeric value') from exc
    if values.size != size:
        raise ValueError(f'Row {row_number}: {field} requires {size} values, got {values.size}')
    return values


def _validate_rotation(rotation, field, row_number):
    matrix = rotation.reshape(3, 3)
    if not np.all(np.isfinite(matrix)) or not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-5):
        raise ValueError(f'Row {row_number}: {field} is not a valid rotation matrix')
    if not np.isclose(np.linalg.det(matrix), 1.0, atol=1e-5):
        raise ValueError(f'Row {row_number}: {field} must have determinant +1')
    return matrix


def read_rows(path):
    """Read a CSV pose dataset and return a list of pose tuples.

    Returns (gripper_r, gripper_t, target_r, target_t) tuples.
    """
    with open(path, newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    required = {'gripper2base_r', 'gripper2base_t', 'target2cam_r', 'target2cam_t'}
    if not rows:
        raise ValueError('CSV contains no data rows')
    if not required.issubset(rows[0]):
        raise ValueError('CSV must contain gripper2base_r/t and target2cam_r/t columns')
    result = []
    for row_number, row in enumerate(rows, start=2):
        if any(not row.get(field, '').strip() for field in required):
            raise ValueError(f'Row {row_number}: all required fields must be non-empty')
        result.append((
            _validate_rotation(
                _parse_values(row['gripper2base_r'], 9, 'gripper2base_r', row_number),
                'gripper2base_r',
                row_number,
            ),
            _parse_values(
                row['gripper2base_t'], 3, 'gripper2base_t', row_number,
            ).reshape(3, 1),
            _validate_rotation(
                _parse_values(row['target2cam_r'], 9, 'target2cam_r', row_number),
                'target2cam_r',
                row_number,
            ),
            _parse_values(
                row['target2cam_t'], 3, 'target2cam_t', row_number,
            ).reshape(3, 1),
        ))
    return result


def rotation_diversity(rotations):
    """Return the maximum consecutive rotation angle (radians) in a sequence."""
    angles = []
    for first, second in zip(rotations, rotations[1:]):
        relative = first.T @ second
        cosine = np.clip((np.trace(relative) - 1.0) / 2.0, -1.0, 1.0)
        angles.append(float(np.arccos(cosine)))
    return max(angles, default=0.0)


def rotation_span(rotations):
    """Return the maximum rotation angle (radians) relative to the first pose."""
    if not rotations:
        return 0.0
    reference = rotations[0]
    angles = []
    for rotation in rotations[1:]:
        relative = reference.T @ rotation
        cosine = np.clip((np.trace(relative) - 1.0) / 2.0, -1.0, 1.0)
        angles.append(float(np.arccos(cosine)))
    return max(angles, default=0.0)


def fallback_calibrate_hand_eye(rows):
    """Solve AX=XB with rotation Kronecker equations when OpenCV lacks the API."""
    relative_pairs = []
    for first, second in zip(rows, rows[1:]):
        first_gripper = homogeneous_matrix(first[0], first[1])
        second_gripper = homogeneous_matrix(second[0], second[1])
        first_target = homogeneous_matrix(first[2], first[3])
        second_target = homogeneous_matrix(second[2], second[3])
        relative_pairs.append((
            np.linalg.inv(first_gripper) @ second_gripper,
            first_target @ np.linalg.inv(second_target),
        ))

    equations = []
    for motion_a, motion_b in relative_pairs:
        equations.append(
            np.kron(np.eye(3), motion_a[:3, :3])
            - np.kron(motion_b[:3, :3].T, np.eye(3))
        )
    _, _, vh = np.linalg.svd(np.vstack(equations))
    rotation_guess = vh[-1].reshape(3, 3, order='F')
    left, _, right = np.linalg.svd(rotation_guess)
    rotation = left @ right
    if np.linalg.det(rotation) < 0.0:
        left[:, -1] *= -1.0
        rotation = left @ right

    translation_equations = []
    translation_values = []
    for motion_a, motion_b in relative_pairs:
        translation_equations.append(motion_a[:3, :3] - np.eye(3))
        translation_values.append(rotation @ motion_b[:3, 3] - motion_a[:3, 3])
    translation = np.linalg.lstsq(
        np.vstack(translation_equations), np.concatenate(translation_values), rcond=None
    )[0].reshape(3, 1)
    return rotation, translation


def solve_hand_eye(rows, algorithm='tsai'):
    """Solve hand-eye calibration from a list of pose pairs.

    Returns (rotation_3x3, translation_3x1).
    """
    if len(rows) < 4:
        raise ValueError('At least 4 pose pairs are required; 10-20 varied poses are recommended')
    if algorithm not in HAND_EYE_ALGORITHMS:
        raise ValueError(
            f'Unknown algorithm {algorithm}; '
            f'choose from {", ".join(HAND_EYE_ALGORITHMS)}'
        )
    gripper_rotations, gripper_translations, target_rotations, target_translations = zip(*rows)
    gripper_rotations = list(gripper_rotations)
    if rotation_diversity(gripper_rotations) < np.deg2rad(5.0):
        raise ValueError(
            'Robot poses have insufficient rotational diversity;'
            ' collect varied orientations'
        )
    if rotation_span(gripper_rotations) < np.deg2rad(15.0):
        raise ValueError(
            'Robot poses have insufficient overall rotational span;'
            ' collect wider orientations'
        )
    if hasattr(cv2, 'calibrateHandEye'):
        result_r, result_t = cv2.calibrateHandEye(
            list(gripper_rotations), list(gripper_translations),
            list(target_rotations), list(target_translations),
            method=HAND_EYE_ALGORITHMS[algorithm],
        )
    else:
        result_r, result_t = fallback_calibrate_hand_eye(rows)
    result_r = np.asarray(result_r, dtype=np.float64).reshape(3, 3)
    result_t = np.asarray(result_t, dtype=np.float64).reshape(3, 1)
    if not np.all(np.isfinite(result_r)) or not np.all(np.isfinite(result_t)):
        raise RuntimeError('OpenCV returned a non-finite hand-eye solution')
    return result_r, result_t


def closed_loop_errors(rows, camera_to_gripper):
    """Compute per-sample closed-loop reprojection errors given camera_to_gripper."""
    transforms = []
    for gripper_r, gripper_t, target_r, target_t in rows:
        base_to_gripper = homogeneous_matrix(gripper_r, gripper_t)
        target_to_camera = homogeneous_matrix(target_r, target_t)
        transforms.append(base_to_gripper @ camera_to_gripper @ target_to_camera)
    reference = transforms[0]
    errors = []
    for transform in transforms:
        delta = np.linalg.inv(reference) @ transform
        translation_error = float(np.linalg.norm(delta[:3, 3]))
        angle = float(np.arccos(np.clip((np.trace(delta[:3, :3]) - 1.0) / 2.0, -1.0, 1.0)))
        errors.append({
            'translation_m': translation_error,
            'rotation_deg': float(np.rad2deg(angle)),
        })
    return errors


def write_handeye_yaml(
    path: str,
    algorithm: str,
    result_r: np.ndarray,
    result_t: np.ndarray,
    camera_to_gripper: np.ndarray,
    gripper_to_camera: np.ndarray,
    sample_count: int,
    errors: list[dict],
    **extra_fields: str,
) -> None:
    """Write hand-eye calibration results to a YAML file via ``cv2.FileStorage``.

    *extra_fields* are written verbatim (e.g. ``base_frame``, ``gripper_frame``).
    """
    import cv2

    storage = cv2.FileStorage(str(path), cv2.FILE_STORAGE_WRITE)
    try:
        if not storage.isOpened():
            raise RuntimeError(f'Cannot write to {path}')

        storage.write('mode', 'eye_in_hand')
        storage.write('algorithm', algorithm)
        for key, value in extra_fields.items():
            storage.write(key, value)
        storage.write('camera_to_gripper_rotation', result_r)
        storage.write('camera_to_gripper_translation_m', result_t)
        storage.write('camera_to_gripper_matrix', camera_to_gripper)
        storage.write('gripper_to_camera_matrix', gripper_to_camera)
        storage.write('sample_count', sample_count)
        mean_trans = float(np.mean([e['translation_m'] for e in errors]))
        max_trans = float(np.max([e['translation_m'] for e in errors]))
        mean_rot = float(np.mean([e['rotation_deg'] for e in errors]))
        max_rot = float(np.max([e['rotation_deg'] for e in errors]))
        storage.write('mean_closed_loop_translation_m', mean_trans)
        storage.write('max_closed_loop_translation_m', max_trans)
        storage.write('mean_closed_loop_rotation_deg', mean_rot)
        storage.write('max_closed_loop_rotation_deg', max_rot)
    finally:
        storage.release()


def should_collect_sample(
    robot_matrix: np.ndarray,
    target_matrix: np.ndarray,
    robot_stamp: float,
    target_stamp: float,
    *,
    sync_tolerance_s: float = 0.1,
    min_translation_m: float = 0.01,
    min_rotation_deg: float = 5.0,
    min_target_motion_m: float = 0.002,
    previous_robot: np.ndarray | None = None,
    previous_target: np.ndarray | None = None,
) -> tuple[bool, float, float]:
    """Decide whether a new synchronized pose pair should be collected.

    Returns ``(should_collect, translation_delta_m, rotation_delta_deg)``.
    Deltas are 0.0 when there is no previous sample to compare against.
    """
    if abs(robot_stamp - target_stamp) > sync_tolerance_s:
        return False, 0.0, 0.0
    if previous_robot is None:
        return True, 0.0, 0.0
    translation_delta = float(np.linalg.norm(robot_matrix[:3, 3] - previous_robot[:3, 3]))
    rotation_delta = rotation_angle(previous_robot[:3, :3].T @ robot_matrix[:3, :3])
    if translation_delta < min_translation_m and math.degrees(rotation_delta) < min_rotation_deg:
        return False, translation_delta, math.degrees(rotation_delta)
    if np.linalg.norm(target_matrix[:3, 3] - previous_target[:3, 3]) < min_target_motion_m:
        return False, translation_delta, math.degrees(rotation_delta)
    return True, translation_delta, math.degrees(rotation_delta)
