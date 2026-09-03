import numpy as np

from aprilgrid_calibration.calibrator import build_yaml, validate_spec
from aprilgrid_calibration.spec import AprilGridSpec


def test_validate_spec_accepts_project_board():
    spec = AprilGridSpec()
    validate_spec(spec)
    assert spec.num_tags == 12


def test_build_yaml_exports_ros_camera_info_shape():
    camera_matrix = np.array([
        [800.0, 0.0, 320.0],
        [0.0, 800.0, 240.0],
        [0.0, 0.0, 1.0],
    ])
    yaml_text = build_yaml(camera_matrix, np.zeros(5), (640, 480))
    assert 'image_width: 640' in yaml_text
    assert 'image_height: 480' in yaml_text
    assert 'distortion_model: plumb_bob' in yaml_text
    assert 'projection_matrix:' in yaml_text
