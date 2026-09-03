#!/usr/bin/env python3
"""CLI entry point for solving eye-in-hand calibration from a CSV pose dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from vision_core import (
    HAND_EYE_ALGORITHMS,
    closed_loop_errors,
    homogeneous_matrix,
    read_rows,
    solve_hand_eye,
    write_handeye_yaml,
)


def main():
    parser = argparse.ArgumentParser(
        description='Solve eye-in-hand calibration from synchronized robot and AprilGrid poses.'
    )
    parser.add_argument('--input', required=True, help='CSV pose dataset')
    parser.add_argument('--output', required=True, help='YAML output path')
    parser.add_argument('--algorithm', choices=tuple(HAND_EYE_ALGORITHMS), default='tsai')
    parser.add_argument('--base-frame', default='base_link')
    parser.add_argument('--gripper-frame', default='tool0')
    parser.add_argument('--camera-frame', default='camera_optical_frame')
    parser.add_argument('--target-frame', default='apriltag_board')
    args = parser.parse_args()

    rows = read_rows(args.input)
    result_r, result_t = solve_hand_eye(rows, args.algorithm)
    camera_to_gripper = homogeneous_matrix(result_r, result_t)
    gripper_to_camera = np.linalg.inv(camera_to_gripper)
    errors = closed_loop_errors(rows, camera_to_gripper)

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    write_handeye_yaml(
        str(output),
        algorithm=args.algorithm,
        result_r=result_r,
        result_t=result_t,
        camera_to_gripper=camera_to_gripper,
        gripper_to_camera=gripper_to_camera,
        sample_count=len(rows),
        errors=errors,
        base_frame=args.base_frame,
        gripper_frame=args.gripper_frame,
        camera_frame=args.camera_frame,
        target_frame=args.target_frame,
    )

    print(f'Wrote eye-in-hand camera_to_gripper result to {output}')
    print(f'Samples: {len(rows)}, algorithm: {args.algorithm}')
    print(f'Mean closed-loop error: {np.mean([item["translation_m"] for item in errors]):.6f} m, '
          f'{np.mean([item["rotation_deg"] for item in errors]):.3f} deg')


if __name__ == '__main__':
    main()
