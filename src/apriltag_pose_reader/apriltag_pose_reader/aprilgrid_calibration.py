"""AprilGrid calibration utilities and CLI for the ROS2 workspace.

This implementation matches the project requirement:
  - 4x3 AprilTag board
  - tag36h11 family
  - 50 mm tag edge length
  - 10 mm gap between adjacent tag borders

It supports:
  1. AprilGrid geometry validation
  2. detection of board corners from RGB/gray images
  3. camera intrinsic calibration using OpenCV
  4. board pose estimation (extrinsic pose per image)
  5. export of a ROS CameraInfo YAML file
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

try:
    from apriltag import apriltag as AprilTagDetector
except Exception as exc:  # pragma: no cover - runtime dependency check
    AprilTagDetector = None
    _APRILTAG_IMPORT_ERROR = exc
else:
    _APRILTAG_IMPORT_ERROR = None

from apriltag_pose_reader.aprilgrid_spec import AprilGridSpec


def _normalize_path(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser().resolve()


def _validate_spec(spec: AprilGridSpec) -> None:
    if spec.rows <= 0 or spec.cols <= 0:
        raise ValueError('rows and cols must be positive integers')
    if spec.tag_size_m <= 0.0:
        raise ValueError('tag_size_m must be positive')
    if spec.tag_spacing_m < 0.0:
        raise ValueError('tag_spacing_m must be non-negative')
    if spec.tag_family.lower() != 'tag36h11':
        raise ValueError('Only tag36h11 is accepted for the current calibration requirement')
    if spec.num_tags != 12:
        raise ValueError(f'Expected 12 tags for a 4x3 board, got {spec.num_tags}')


class AprilGridCalibrator:
    """Detect AprilTag corners on an AprilGrid and estimate camera intrinsics."""

    def __init__(self, spec: AprilGridSpec | None = None) -> None:
        if AprilTagDetector is None:
            raise RuntimeError(
                'AprilTag library is not available in the current Python environment. '
                f'Original error: {_APRILTAG_IMPORT_ERROR}'
            )
        self.spec = spec or AprilGridSpec()
        _validate_spec(self.spec)
        self.detector = AprilTagDetector(self.spec.tag_family)

    def board_corner_positions(self, tag_id: int) -> np.ndarray:
        row = tag_id // self.spec.cols
        col = tag_id % self.spec.cols
        x0 = col * self.spec.tag_center_spacing_m
        y0 = row * self.spec.tag_center_spacing_m
        size = self.spec.tag_size_m
        return np.array(
            [
                [x0, y0 + size, 0.0],
                [x0 + size, y0 + size, 0.0],
                [x0 + size, y0, 0.0],
                [x0, y0, 0.0],
            ],
            dtype=np.float64,
        )

    def detect_board(self, gray_image: np.ndarray) -> list[dict]:
        image = np.asarray(gray_image)
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if image.ndim != 2:
            raise ValueError('AprilTag detection requires a 2D grayscale image')
        detections = self.detector.detect(image)
        return [d for d in detections if 0 <= int(d['id']) < self.spec.num_tags]

    def tag_image_points(self, detection: dict) -> np.ndarray:
        corners = np.asarray(detection['lb-rb-rt-lt'], dtype=np.float64)
        if corners.shape != (4, 2):
            raise ValueError(f'Unexpected AprilTag corner shape: {corners.shape}')
        return corners

    def build_observation_data(self, image: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
        detections = self.detect_board(image)
        object_points: list[np.ndarray] = []
        image_points: list[np.ndarray] = []
        for det in detections:
            tag_id = int(det['id'])
            object_points.append(self.board_corner_positions(tag_id))
            image_points.append(self.tag_image_points(det))
        return object_points, image_points

    def solve_board_pose(
        self,
        object_points: np.ndarray,
        image_points: np.ndarray,
        camera_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
    ) -> tuple[bool, np.ndarray, np.ndarray]:
        success, rvec, tvec = cv2.solvePnP(
            object_points,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        return success, rvec, tvec

    def calibrate_from_images(
        self,
        image_paths: list[str | os.PathLike[str]],
        image_size: tuple[int, int] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, list[dict]]:
        object_points_list: list[np.ndarray] = []
        image_points_list: list[np.ndarray] = []
        extrinsics: list[dict] = []

        if not image_paths:
            raise ValueError('At least one image path is required for calibration')

        for image_path in image_paths:
            image = cv2.imread(str(_normalize_path(image_path)), cv2.IMREAD_COLOR)
            if image is None:
                raise FileNotFoundError(f'Could not read calibration image: {image_path}')
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            object_points, image_points = self.build_observation_data(gray)
            if not object_points:
                continue

            obj_flat = np.concatenate(object_points, axis=0).astype(np.float64)
            img_flat = np.concatenate(image_points, axis=0).astype(np.float64)

            object_points_list.append(obj_flat.astype(np.float32))
            image_points_list.append(img_flat.reshape(-1, 1, 2).astype(np.float32))

            if image_size is None:
                height, width = image.shape[:2]
            else:
                height, width = image_size

            initial_K = np.eye(3, dtype=np.float64)
            initial_K[0, 0] = max(width, 1)
            initial_K[1, 1] = max(height, 1)
            initial_K[0, 2] = width / 2.0
            initial_K[1, 2] = height / 2.0
            initial_D = np.zeros((5,), dtype=np.float64)

            success, rvec, tvec = self.solve_board_pose(obj_flat, img_flat, initial_K, initial_D)
            if success:
                extrinsics.append(
                    {
                        'image_path': str(image_path),
                        'rvec': np.asarray(rvec, dtype=np.float64).reshape(3).tolist(),
                        'tvec': np.asarray(tvec, dtype=np.float64).reshape(3).tolist(),
                    }
                )

        if len(object_points_list) < 3:
            raise ValueError('Need at least 3 calibration images with visible AprilTags')

        first_image = cv2.imread(str(_normalize_path(image_paths[0])), cv2.IMREAD_COLOR)
        if first_image is None:
            raise FileNotFoundError(f'Could not read calibration image: {image_paths[0]}')
        height, width = image_size if image_size is not None else first_image.shape[:2]

        initial_K = np.eye(3, dtype=np.float64)
        initial_K[0, 0] = max(width, 1)
        initial_K[1, 1] = max(height, 1)
        initial_K[0, 2] = width / 2.0
        initial_K[1, 2] = height / 2.0
        initial_D = np.zeros((5,), dtype=np.float64)

        ret, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
            object_points_list,
            image_points_list,
            (width, height),
            initial_K,
            initial_D,
            flags=cv2.CALIB_USE_INTRINSIC_GUESS,
        )

        if ret is None or ret <= 0.0:
            raise RuntimeError('Camera calibration failed: no valid solution was found')

        return camera_matrix, dist_coeffs, extrinsics


def _build_yaml(camera_matrix: np.ndarray, dist_coeffs: np.ndarray, image_size: tuple[int, int]) -> str:
    width, height = image_size
    if camera_matrix.shape != (3, 3):
        raise ValueError('camera_matrix must be 3x3')
    flat_k = [float(v) for v in camera_matrix.reshape(-1).tolist()]
    flat_d = [float(v) for v in np.asarray(dist_coeffs, dtype=np.float64).reshape(-1).tolist()]
    rect = np.eye(3, dtype=np.float64).reshape(-1).tolist()
    proj = np.hstack([camera_matrix, np.zeros((3, 1), dtype=np.float64)]).reshape(-1).tolist()
    mapping = {
        'image_width': width,
        'image_height': height,
        'camera_name': 'apriltag_calibration',
        'camera_matrix': {'rows': 3, 'cols': 3, 'data': flat_k},
        'distortion_model': 'plumb_bob',
        'distortion_coefficients': {'rows': 1, 'cols': len(flat_d), 'data': flat_d},
        'rectification_matrix': {'rows': 3, 'cols': 3, 'data': rect},
        'projection_matrix': {'rows': 3, 'cols': 4, 'data': proj},
    }
    if yaml is None:
        return json.dumps(mapping, indent=2, sort_keys=True)
    return yaml.safe_dump(mapping, sort_keys=False, default_flow_style=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Calibrate a camera from multiple AprilGrid images.')
    parser.add_argument('images', nargs='+', help='Paths to calibration images containing the AprilGrid')
    parser.add_argument('--rows', type=int, default=4, help='AprilTag board rows (default: 4)')
    parser.add_argument('--cols', type=int, default=3, help='AprilTag board cols (default: 3)')
    parser.add_argument('--tag-size-m', type=float, default=0.05, help='Tag edge length in meters (default: 0.05)')
    parser.add_argument('--tag-spacing-m', type=float, default=0.01, help='Tag border gap in meters (default: 0.01)')
    parser.add_argument('--tag-family', type=str, default='tag36h11', help='Tag family (default: tag36h11)')
    parser.add_argument('--output', type=str, default='camera_calibration.yaml', help='Output path for camera calibration YAML')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    spec = AprilGridSpec(
        rows=args.rows,
        cols=args.cols,
        tag_size_m=args.tag_size_m,
        tag_spacing_m=args.tag_spacing_m,
        tag_family=args.tag_family,
    )
    _validate_spec(spec)

    try:
        calibrator = AprilGridCalibrator(spec)
        if len(args.images) < 3:
            raise ValueError('At least three calibration images are required to estimate a stable camera model')

        first_image = cv2.imread(str(_normalize_path(args.images[0])), cv2.IMREAD_COLOR)
        if first_image is None:
            raise FileNotFoundError(f'Could not read calibration image: {args.images[0]}')
        height, width = first_image.shape[:2]

        K, D, extrinsics = calibrator.calibrate_from_images(args.images, image_size=(height, width))
        calibration_yaml = _build_yaml(K, D, (width, height))
        output_path = _normalize_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(calibration_yaml, encoding='utf-8')

        summary = {
            'board_type': 'AprilGrid',
            'rows': spec.rows,
            'cols': spec.cols,
            'num_tags': spec.num_tags,
            'tag_family': spec.tag_family,
            'tag_size_m': spec.tag_size_m,
            'tag_spacing_m': spec.tag_spacing_m,
            'camera_matrix': K.tolist(),
            'distortion_coefficients': D.tolist(),
            'images_used': len(extrinsics),
            'output_yaml': str(output_path),
            'extrinsics': extrinsics,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except Exception as exc:  # pragma: no cover
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
