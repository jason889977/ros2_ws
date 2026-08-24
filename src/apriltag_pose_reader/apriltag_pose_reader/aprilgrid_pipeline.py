"""End-to-end AprilGrid calibration pipeline for the ROS2 workspace.

This module ties together the full sequence:
  1. collect calibration images
  2. detect all AprilTags in each image
  3. estimate camera intrinsic parameters
  4. estimate board pose in each frame
  5. write a ROS-compatible CameraInfo YAML
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from apriltag_pose_reader.aprilgrid_calibration import AprilGridCalibrator, _build_yaml, _validate_spec
from apriltag_pose_reader.aprilgrid_capture import collect_images
from apriltag_pose_reader.aprilgrid_spec import AprilGridSpec


def run_pipeline(
    input_dir: str,
    output_dir: str,
    rows: int = 4,
    cols: int = 3,
    tag_size_m: float = 0.05,
    tag_spacing_m: float = 0.01,
    tag_family: str = 'tag36h11',
    output_name: str = 'camera_calibration.yaml',
) -> dict:
    spec = AprilGridSpec(rows=rows, cols=cols, tag_size_m=tag_size_m, tag_spacing_m=tag_spacing_m, tag_family=tag_family)
    _validate_spec(spec)
    collected = collect_images(input_dir, output_dir, prefix='calib_')
    if not collected:
        raise RuntimeError(f'No calibration images were found in {input_dir}')

    calibrator = AprilGridCalibrator(spec)
    first_image = cv2.imread(collected[0], cv2.IMREAD_COLOR)
    if first_image is None:
        raise FileNotFoundError(f'Could not read calibration image: {collected[0]}')
    height, width = first_image.shape[:2]

    K, D, extrinsics = calibrator.calibrate_from_images(collected, image_size=(height, width))
    yaml_text = _build_yaml(K, D, (width, height))
    out_path = Path(output_dir) / output_name
    out_path.write_text(yaml_text, encoding='utf-8')

    return {
        'input_dir': input_dir,
        'output_dir': str(output_dir),
        'output_yaml': str(out_path),
        'rows': spec.rows,
        'cols': spec.cols,
        'tag_family': spec.tag_family,
        'tag_size_m': spec.tag_size_m,
        'tag_spacing_m': spec.tag_spacing_m,
        'camera_matrix': K.tolist(),
        'distortion_coefficients': D.tolist(),
        'images_used': len(extrinsics),
        'extrinsics': extrinsics,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run the complete AprilGrid calibration pipeline.')
    parser.add_argument('input_dir', help='Directory containing calibration images')
    parser.add_argument('--output-dir', default='calibration_output', help='Directory to store collected images and YAML output')
    parser.add_argument('--rows', type=int, default=4, help='Number of AprilTag rows (default: 4)')
    parser.add_argument('--cols', type=int, default=3, help='Number of AprilTag columns (default: 3)')
    parser.add_argument('--tag-size-m', type=float, default=0.05, help='Tag edge length in meters (default: 0.05)')
    parser.add_argument('--tag-spacing-m', type=float, default=0.01, help='Board tag spacing in meters (default: 0.01)')
    parser.add_argument('--tag-family', type=str, default='tag36h11', help='Tag family (default: tag36h11)')
    parser.add_argument('--output-name', type=str, default='camera_calibration.yaml', help='Filename for the generated camera calibration YAML')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    result = run_pipeline(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        rows=args.rows,
        cols=args.cols,
        tag_size_m=args.tag_size_m,
        tag_spacing_m=args.tag_spacing_m,
        tag_family=args.tag_family,
        output_name=args.output_name,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
