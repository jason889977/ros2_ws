#!/usr/bin/env python3
"""Solve eye-in-hand calibration from synchronized robot and AprilGrid poses.

CSV columns use OpenCV's convention: ``gripper2base`` is the gripper pose in
the robot base frame and ``target2cam`` is the AprilGrid pose in the camera
frame. Translation values are expressed in meters.
"""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np


ALGORITHMS = {
    'tsai': cv2.CALIB_HAND_EYE_TSAI,
    'park': cv2.CALIB_HAND_EYE_PARK,
    'horaud': cv2.CALIB_HAND_EYE_HORAUD,
    'daniilidis': cv2.CALIB_HAND_EYE_DANIILIDIS,
}


def _parse_values(value, size, field, row_number):
    try:
        values = np.asarray([float(item) for item in value.replace(',', ' ').split()], dtype=np.float64)
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
            _validate_rotation(_parse_values(row['gripper2base_r'], 9, 'gripper2base_r', row_number), 'gripper2base_r', row_number),
            _parse_values(row['gripper2base_t'], 3, 'gripper2base_t', row_number).reshape(3, 1),
            _validate_rotation(_parse_values(row['target2cam_r'], 9, 'target2cam_r', row_number), 'target2cam_r', row_number),
            _parse_values(row['target2cam_t'], 3, 'target2cam_t', row_number).reshape(3, 1),
        ))
    return result


def _homogeneous(rotation, translation):
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = rotation
    result[:3, 3] = np.asarray(translation, dtype=np.float64).reshape(3)
    return result


def _rotation_diversity(rotations):
    angles = []
    for first, second in zip(rotations, rotations[1:]):
        relative = first.T @ second
        cosine = np.clip((np.trace(relative) - 1.0) / 2.0, -1.0, 1.0)
        angles.append(float(np.arccos(cosine)))
    return max(angles, default=0.0)


def _fallback_calibrate_hand_eye(rows):
    """Solve AX=XB with rotation Kronecker equations when OpenCV lacks the API."""
    relative_pairs = []
    for first, second in zip(rows, rows[1:]):
        first_gripper = _homogeneous(first[0], first[1])
        second_gripper = _homogeneous(second[0], second[1])
        first_target = _homogeneous(first[2], first[3])
        second_target = _homogeneous(second[2], second[3])
        relative_pairs.append((
            np.linalg.inv(first_gripper) @ second_gripper,
            first_target @ np.linalg.inv(second_target),
        ))

    equations = []
    for motion_a, motion_b in relative_pairs:
        equations.append(np.kron(np.eye(3), motion_a[:3, :3]) - np.kron(motion_b[:3, :3].T, np.eye(3)))
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


def solve(rows, algorithm='tsai'):
    if len(rows) < 4:
        raise ValueError('At least 4 pose pairs are required; 10-20 varied poses are recommended')
    if algorithm not in ALGORITHMS:
        raise ValueError(f'Unknown algorithm {algorithm}; choose from {", ".join(ALGORITHMS)}')
    gripper_rotations, gripper_translations, target_rotations, target_translations = zip(*rows)
    if _rotation_diversity(list(gripper_rotations)) < np.deg2rad(5.0):
        raise ValueError('Robot poses have insufficient rotational diversity; collect varied orientations')
    if hasattr(cv2, 'calibrateHandEye'):
        result_r, result_t = cv2.calibrateHandEye(
            list(gripper_rotations), list(gripper_translations),
            list(target_rotations), list(target_translations), method=ALGORITHMS[algorithm]
        )
    else:
        result_r, result_t = _fallback_calibrate_hand_eye(rows)
    result_r = np.asarray(result_r, dtype=np.float64).reshape(3, 3)
    result_t = np.asarray(result_t, dtype=np.float64).reshape(3, 1)
    if not np.all(np.isfinite(result_r)) or not np.all(np.isfinite(result_t)):
        raise RuntimeError('OpenCV returned a non-finite hand-eye solution')
    return result_r, result_t


def _closed_loop_errors(rows, camera_to_gripper):
    transforms = []
    for gripper_r, gripper_t, target_r, target_t in rows:
        base_to_gripper = _homogeneous(gripper_r, gripper_t)
        target_to_camera = _homogeneous(target_r, target_t)
        transforms.append(base_to_gripper @ camera_to_gripper @ target_to_camera)
    reference = transforms[0]
    errors = []
    for transform in transforms:
        delta = np.linalg.inv(reference) @ transform
        translation_error = float(np.linalg.norm(delta[:3, 3]))
        angle = float(np.arccos(np.clip((np.trace(delta[:3, :3]) - 1.0) / 2.0, -1.0, 1.0)))
        errors.append({'translation_m': translation_error, 'rotation_deg': float(np.rad2deg(angle))})
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, help='CSV pose dataset')
    parser.add_argument('--output', required=True, help='YAML output path')
    parser.add_argument('--algorithm', choices=tuple(ALGORITHMS), default='tsai')
    parser.add_argument('--base-frame', default='base_link')
    parser.add_argument('--gripper-frame', default='tool0')
    parser.add_argument('--camera-frame', default='camera_optical_frame')
    parser.add_argument('--target-frame', default='apriltag_board')
    args = parser.parse_args()
    rows = read_rows(args.input)
    result_r, result_t = solve(rows, args.algorithm)
    camera_to_gripper = _homogeneous(result_r, result_t)
    gripper_to_camera = np.linalg.inv(camera_to_gripper)
    errors = _closed_loop_errors(rows, camera_to_gripper)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    storage = cv2.FileStorage(args.output, cv2.FILE_STORAGE_WRITE)
    storage.write('mode', 'eye_in_hand')
    storage.write('algorithm', args.algorithm)
    storage.write('base_frame', args.base_frame)
    storage.write('gripper_frame', args.gripper_frame)
    storage.write('camera_frame', args.camera_frame)
    storage.write('target_frame', args.target_frame)
    storage.write('camera_to_gripper_rotation', result_r)
    storage.write('camera_to_gripper_translation_m', result_t)
    storage.write('camera_to_gripper_matrix', camera_to_gripper)
    storage.write('gripper_to_camera_matrix', gripper_to_camera)
    storage.write('sample_count', len(rows))
    storage.write('mean_closed_loop_translation_m', float(np.mean([item['translation_m'] for item in errors])))
    storage.write('max_closed_loop_translation_m', float(np.max([item['translation_m'] for item in errors])))
    storage.write('mean_closed_loop_rotation_deg', float(np.mean([item['rotation_deg'] for item in errors])))
    storage.write('max_closed_loop_rotation_deg', float(np.max([item['rotation_deg'] for item in errors])))
    storage.release()
    print(f'Wrote eye-in-hand camera_to_gripper result to {args.output}')
    print(f'Samples: {len(rows)}, algorithm: {args.algorithm}')
    print(f'Mean closed-loop error: {np.mean([item["translation_m"] for item in errors]):.6f} m, '
          f'{np.mean([item["rotation_deg"] for item in errors]):.3f} deg')


if __name__ == '__main__':
    main()
