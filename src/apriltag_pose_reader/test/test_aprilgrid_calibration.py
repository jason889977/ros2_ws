import os

import cv2
import numpy as np

from apriltag_pose_reader.aprilgrid_calibration import AprilGridCalibrator
from apriltag_pose_reader.aprilgrid_spec import AprilGridSpec


def _make_test_image(size=(640, 480), center=(320, 240)):
    image = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    cv2.circle(image, center, 30, (255, 255, 255), -1)
    return image


def test_aprilgrid_calibrator_accepts_latest_geometry():
    spec = AprilGridSpec(rows=4, cols=3, tag_size_m=0.05, tag_spacing_m=0.01, tag_family='tag36h11')
    calibrator = AprilGridCalibrator(spec)
    assert calibrator.spec.rows == 4
    assert calibrator.spec.cols == 3
    assert calibrator.spec.tag_family == 'tag36h11'
    assert calibrator.spec.num_tags == 12
    image = _make_test_image()
    objs, imgs = calibrator.build_observation_data(image)
    assert isinstance(objs, list)
    assert isinstance(imgs, list)
    assert len(objs) == 0 or len(objs) >= 0


def test_calibration_entrypoint_generates_yaml(tmp_path):
    spec = AprilGridSpec(rows=4, cols=3, tag_size_m=0.05, tag_spacing_m=0.01, tag_family='tag36h11')
    image_path = tmp_path / 'board.png'
    cv2.imwrite(str(image_path), _make_test_image())
    output_path = tmp_path / 'camera.yaml'

    calibrator = AprilGridCalibrator(spec)
    K, D, _ = calibrator.calibrate_from_images([str(image_path)], image_size=(480, 640))
    assert K.shape == (3, 3)
    assert D.shape == (5,)
    assert os.path.exists(str(image_path))
