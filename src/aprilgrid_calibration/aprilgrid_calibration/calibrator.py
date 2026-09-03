"""AprilGrid detection, camera calibration, and ROS YAML export."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import cv2
import numpy as np

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

try:
    from apriltag import apriltag as AprilTagDetector
except (ImportError, OSError) as exc:  # pragma: no cover
    AprilTagDetector = None
    _APRILTAG_IMPORT_ERROR = exc
else:
    _APRILTAG_IMPORT_ERROR = None

from .spec import AprilGridSpec


class _CalibrationCancelledError(Exception):
    pass


def normalize_path(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser().resolve()


def validate_spec(
    spec: AprilGridSpec,
    required_tag_family: str | None = 'tag36h11',
) -> None:
    if spec.rows <= 0 or spec.cols <= 0:
        raise ValueError('rows and cols must be positive integers')
    if spec.tag_size_m <= 0.0:
        raise ValueError('tag_size_m must be positive')
    if spec.tag_spacing_m < 0.0:
        raise ValueError('tag_spacing_m must be non-negative')
    if required_tag_family is not None and spec.tag_family.lower() != required_tag_family:
        raise ValueError(
            f'Only {required_tag_family} is accepted '
            f'for the current calibration requirement')


class AprilGridCalibrator:
    """Detect AprilTag corners and estimate camera intrinsics."""

    def __init__(self, spec: AprilGridSpec | None = None) -> None:
        if AprilTagDetector is None:
            raise RuntimeError(
                'AprilTag library is not available in the current Python environment. '
                f'Original error: {_APRILTAG_IMPORT_ERROR}'
            )
        self.spec = spec or AprilGridSpec()
        validate_spec(self.spec)
        self.detector = AprilTagDetector(self.spec.tag_family)

    def board_corner_positions(self, tag_id: int) -> np.ndarray:
        return self.spec.tag_corner_points_apriltag_order(tag_id)

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

    def _refine_corners(self, gray_image: np.ndarray, corners: np.ndarray) -> np.ndarray:
        """Sub-pixel refinement for detected tag corners."""
        refined = corners.astype(np.float32).reshape(-1, 1, 2)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
        cv2.cornerSubPix(gray_image, refined, (5, 5), (-1, -1), criteria)
        return refined.reshape(-1, 2).astype(np.float64)

    def build_observation_data(
        self, image: np.ndarray,
    ) -> tuple[list[np.ndarray], list[np.ndarray]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        object_points: list[np.ndarray] = []
        image_points: list[np.ndarray] = []
        for detection in self.detect_board(image):
            object_points.append(self.board_corner_positions(int(detection['id'])))
            raw_corners = self.tag_image_points(detection)
            image_points.append(self._refine_corners(gray, raw_corners))
        return object_points, image_points

    def solve_board_pose(self, object_points, image_points, camera_matrix, dist_coeffs):
        return cv2.solvePnP(
            object_points, image_points, camera_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

    def _detect_and_accumulate(self, image_paths, progress_callback, cancel_callback):
        """Detect tags in each image and accumulate point correspondences."""
        object_points_list = []
        image_points_list = []

        for index, image_path in enumerate(image_paths):
            if cancel_callback is not None and cancel_callback():
                raise _CalibrationCancelledError()
            image = cv2.imread(str(normalize_path(image_path)), cv2.IMREAD_COLOR)
            if image is None:
                raise FileNotFoundError(f'Could not read calibration image: {image_path}')
            object_points, image_points = self.build_observation_data(image)
            if progress_callback is not None:
                progress_callback(index + 1, len(object_points))
            if not object_points:
                continue
            obj_flat = np.concatenate(object_points, axis=0).astype(np.float32)
            img_flat = np.concatenate(image_points, axis=0).astype(np.float32)
            if obj_flat.shape[0] < 8:
                print(
                    f'Warning: Image {image_path}: '
                    f'fewer than 8 corners, skipping',
                    file=sys.stderr)
                continue
            object_points_list.append(obj_flat.reshape(-1, 1, 3))
            image_points_list.append(img_flat.reshape(-1, 1, 2))

        return object_points_list, image_points_list

    def _run_calibration(self, object_points_list, image_points_list, image_size):
        """Run camera calibration from accumulated point correspondences."""
        if len(object_points_list) < 3:
            raise ValueError('Need at least 3 calibration images with visible AprilTags')
        if image_size is None:
            raise ValueError('image_size is required for calibration')
        height, width = image_size
        ret, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
            object_points_list, image_points_list, (width, height),
            _initial_camera_matrix(width, height), np.zeros((5,), dtype=np.float64),
            flags=cv2.CALIB_USE_INTRINSIC_GUESS,
        )
        if ret is None or ret <= 0.0:
            raise RuntimeError('Camera calibration failed: no valid solution was found')
        return camera_matrix, dist_coeffs, float(ret), len(object_points_list)

    def calibrate_from_images(
        self,
        image_paths,
        image_size=None,
        progress_callback=None,
        cancel_callback=None,
        max_per_image_error: float = 0.0,
    ):
        if not image_paths:
            raise ValueError('At least one image path is required for calibration')

        object_points_list, image_points_list = self._detect_and_accumulate(
            image_paths, progress_callback, cancel_callback,
        )

        if cancel_callback is not None and cancel_callback():
            raise _CalibrationCancelledError()

        camera_matrix, dist_coeffs, ret, good_count = self._run_calibration(
            object_points_list, image_points_list, image_size,
        )

        if max_per_image_error > 0.0 and len(object_points_list) > 3:
            camera_matrix, dist_coeffs, ret, good_count = self._reject_outliers(
                object_points_list, image_points_list, image_size,
                camera_matrix, dist_coeffs, max_per_image_error,
            )

        return camera_matrix, dist_coeffs, ret, good_count

    def _reject_outliers(
        self, object_points_list, image_points_list, image_size,
        camera_matrix, dist_coeffs, max_error: float,
    ):
        """Remove images whose per-image reprojection error exceeds threshold."""
        height, width = image_size
        errors = []
        for obj_pts, img_pts in zip(object_points_list, image_points_list):
            obj_flat = obj_pts.reshape(-1, 3)
            img_flat = img_pts.reshape(-1, 2)
            ok, rvec, tvec = cv2.solvePnP(
                obj_flat, img_flat, camera_matrix, dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE)
            if not ok:
                errors.append(float('inf'))
                continue
            projected, _ = cv2.projectPoints(obj_flat, rvec, tvec, camera_matrix, dist_coeffs)
            err = float(np.linalg.norm(img_flat - projected.reshape(-1, 2), axis=1).mean())
            errors.append(err)

        keep = [i for i, e in enumerate(errors) if e <= max_error]
        if len(keep) < 3 or len(keep) == len(errors):
            return camera_matrix, dist_coeffs, float(
                np.mean(errors)), len(object_points_list)

        kept_obj = [object_points_list[i] for i in keep]
        kept_img = [image_points_list[i] for i in keep]
        ret, new_K, new_D, _, _ = cv2.calibrateCamera(
            kept_obj, kept_img, (width, height),
            camera_matrix.copy(), dist_coeffs.copy(),
            flags=cv2.CALIB_USE_INTRINSIC_GUESS,
        )
        if ret is not None and ret > 0.0 and ret <= float(np.mean(errors)):
            return new_K, new_D, float(ret), len(kept_obj)
        return camera_matrix, dist_coeffs, float(
            np.mean(errors)), len(object_points_list)


def _initial_camera_matrix(width: int, height: int) -> np.ndarray:
    if width <= 0 or height <= 0:
        raise ValueError(f'Invalid image dimensions: {width}x{height}')
    matrix = np.eye(3, dtype=np.float64)
    # Use diagonal length as focal length estimate — closer to real focal lengths
    # than using raw width/height, and improves convergence with CALIB_USE_INTRINSIC_GUESS.
    diagonal = float(np.sqrt(width ** 2 + height ** 2))
    matrix[0, 0] = diagonal
    matrix[1, 1] = diagonal
    matrix[0, 2] = width / 2.0
    matrix[1, 2] = height / 2.0
    return matrix


def build_yaml(
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    image_size: tuple[int, int],
    camera_name: str = 'apriltag_calibration',
) -> str:
    width, height = image_size
    if camera_matrix.shape != (3, 3):
        raise ValueError('camera_matrix must be 3x3')
    flat_k = [float(value) for value in camera_matrix.reshape(-1)]
    flat_d = [float(value) for value in np.asarray(dist_coeffs).reshape(-1)]
    if not all(np.isfinite(flat_k)) or not all(np.isfinite(flat_d)):
        raise ValueError('Calibration produced non-finite values; check input data')
    # cv2.calibrateCamera always outputs the pinhole plumb_bob-style model
    # (4 or 5 coefficients); equidistant only applies to cv2.fisheye.
    _distortion_models = {
        4: 'plumb_bob', 5: 'plumb_bob', 8: 'rational_polynomials',
        12: 'thin_prism', 14: 'thin_prism',
    }
    distortion_model = _distortion_models.get(len(flat_d), 'plumb_bob')
    mapping = {
        'image_width': width,
        'image_height': height,
        'camera_name': camera_name,
        'camera_matrix': {'rows': 3, 'cols': 3, 'data': flat_k},
        'distortion_model': distortion_model,
        'distortion_coefficients': {'rows': 1, 'cols': len(flat_d), 'data': flat_d},
        'rectification_matrix': {'rows': 3, 'cols': 3, 'data': np.eye(3).reshape(-1).tolist()},
        'projection_matrix': {
            'rows': 3, 'cols': 4,
            'data': np.hstack([camera_matrix, np.zeros((3, 1))]).reshape(-1).tolist(),
        },
    }
    if yaml is None:
        raise RuntimeError('pyyaml is required for YAML output; install with: pip install pyyaml')
    return yaml.safe_dump(mapping, sort_keys=False)
